import base64
import json
import readline  # input()에서 한글을 백스페이스로 지울 때 바이트가 남지 않도록 글자 단위 편집 사용
import sys
from enum import Enum
from pathlib import Path
from kiwipiepy import Kiwi
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# 1. 플루치크(Plutchik)의 8가지 기본 감정을 고정된 값(Enum)으로 정의합니다.
class Emotion(str, Enum):
    JOY = "JOY"                     # 기쁨
    TRUST = "TRUST"                 # 신뢰
    FEAR = "FEAR"                   # 공포
    SURPRISE = "SURPRISE"           # 놀람
    SADNESS = "SADNESS"             # 슬픔
    DISGUST = "DISGUST"             # 혐오
    ANGER = "ANGER"                 # 분노
    ANTICIPATION = "ANTICIPATION"   # 기대

# 출력용: 감정별 한글 이름
EMOTION_DISPLAY = {
    Emotion.JOY: "기쁨",
    Emotion.TRUST: "신뢰",
    Emotion.FEAR: "공포",
    Emotion.SURPRISE: "놀람",
    Emotion.SADNESS: "슬픔",
    Emotion.DISGUST: "혐오",
    Emotion.ANGER: "분노",
    Emotion.ANTICIPATION: "기대",
}

# 플루치크의 합성 감정: 두 기본 감정의 조합 → 합성 감정 이름 (순서 무관)
E = Emotion
COMPOSITE_EMOTIONS = {
    # 1차 이중감정 (인접한 감정)
    frozenset({E.JOY, E.TRUST}): "사랑",
    frozenset({E.TRUST, E.FEAR}): "순종",
    frozenset({E.FEAR, E.SURPRISE}): "경외",
    frozenset({E.SURPRISE, E.SADNESS}): "반감",
    frozenset({E.SADNESS, E.DISGUST}): "자책",
    frozenset({E.DISGUST, E.ANGER}): "경멸",
    frozenset({E.ANGER, E.ANTICIPATION}): "공격성",
    frozenset({E.ANTICIPATION, E.JOY}): "낙관",
    # 2차 이중감정 (한 칸 건너뛴 감정)
    frozenset({E.JOY, E.FEAR}): "죄책감",
    frozenset({E.FEAR, E.SADNESS}): "절망",
    frozenset({E.SADNESS, E.ANGER}): "시기",
    frozenset({E.ANGER, E.JOY}): "자부심",
    frozenset({E.TRUST, E.SURPRISE}): "호기심",
    frozenset({E.SURPRISE, E.DISGUST}): "불신",
    frozenset({E.DISGUST, E.ANTICIPATION}): "냉소",
    frozenset({E.ANTICIPATION, E.TRUST}): "희망",
    # 3차 이중감정 (두 칸 건너뛴 감정)
    frozenset({E.JOY, E.SURPRISE}): "큰 기쁨",
    frozenset({E.SURPRISE, E.ANGER}): "격분",
    frozenset({E.ANGER, E.TRUST}): "우월감",
    frozenset({E.TRUST, E.SADNESS}): "감상적임",
    frozenset({E.SADNESS, E.ANTICIPATION}): "비관",
    frozenset({E.ANTICIPATION, E.FEAR}): "염려",
    frozenset({E.FEAR, E.DISGUST}): "수치심",
    frozenset({E.DISGUST, E.JOY}): "불건전한 흥미",
    # 반대되는 감정의 결합
    frozenset({E.JOY, E.SADNESS}): "씁쓸함",
    frozenset({E.TRUST, E.DISGUST}): "애증",
    frozenset({E.FEAR, E.ANGER}): "얼어붙음",
    frozenset({E.SURPRISE, E.ANTICIPATION}): "혼란스러움",
}

# 리소스 기준 폴더 (PyInstaller 빌드 시에는 _MEIPASS 기준)
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

# 감정별 테루테루보즈 이미지 폴더
EMOTION_IMAGE_DIR = BASE_DIR / "emotions"

# 신조어별 예시 대화 사전 (KoCulture-Dialogues, build_neologisms.py로 생성)
NEOLOGISMS = json.loads((BASE_DIR / "data" / "neologisms.json").read_text())

def find_neologisms(text: str) -> list[str]:
    # 한 글자 신조어는 일반 단어에 너무 자주 걸리므로 두 글자 이상만 찾습니다.
    return [word for word in NEOLOGISMS if len(word) >= 2 and word in text]

# 감성사전 (build_sentiment.py로 생성). 교수님 연구 자료라 저장소에 없으므로, 파일이 없으면 감성사전 없이 판독합니다.
SENTIMENT_PATH = BASE_DIR / "data" / "sentiment.json"
SENTIMENT = json.loads(SENTIMENT_PATH.read_text()) if SENTIMENT_PATH.exists() else {}
kiwi = Kiwi() if SENTIMENT else None

def find_sentiment_words(text: str) -> list[str]:
    if not SENTIMENT:
        return []
    # 형태소 분석으로 활용형을 기본형으로 돌려 사전과 맞춥니다. (슬퍼서 → 슬프다, 우울하고 → 우울하다)
    tokens = kiwi.tokenize(text)
    found = []
    for i, token in enumerate(tokens):
        candidates = []
        if token.tag in ("VV", "VA"):
            candidates.append(token.form + "다")
        elif token.tag in ("NNG", "NNP", "XR", "MAG"):
            # 명사 + 하다/되다/스럽다 등 파생어가 사전에 있으면 그쪽을 우선합니다.
            if i + 1 < len(tokens) and tokens[i + 1].tag in ("XSA", "XSV"):
                candidates.append(token.form + tokens[i + 1].form + "다")
            # 한 글자 명사·부사는 일반 단어와 너무 자주 겹쳐 제외합니다.
            if len(token.form) >= 2:
                candidates.append(token.form)
        for word in candidates:
            if word in SENTIMENT:
                if word not in found:
                    found.append(word)
                break
    return found

def sentiment_reference(words: list[str]) -> str:
    lines = ["[참고: 감성사전. 1=매우 부정 ~ 7=매우 긍정, 단어의 사전적 극성이며 문맥이 우선]"]
    for word in words:
        for score, meaning in SENTIMENT[word]:
            lines.append(f"- {word}({score}): {meaning}")
    return "\n".join(lines)

def build_state(text: str, neologisms: list[str], extra_reference: str = "") -> str:
    # 신조어가 있으면 용례를 참고 자료로 덧붙여 모델이 뜻을 파악할 수 있게 합니다.
    if not neologisms and not extra_reference:
        return text
    lines = ["[분석할 문장]", text]
    if neologisms:
        lines += ["", "[참고: 위 문장에 쓰인 신조어의 용례. 감정 판단 대상이 아니며 신조어의 뜻을 이해하는 데만 사용]"]
        for word in neologisms:
            for question, answer in NEOLOGISMS[word]:
                lines.append(f"- {word}: \"{question}\" / \"{answer}\"")
    if extra_reference:
        lines += ["", extra_reference]
    return "\n".join(lines)

def print_emotion_image(emotion: Emotion):
    # iTerm2 인라인 이미지 프로토콜로 출력 (이미지가 없는 감정은 생략)
    path = EMOTION_IMAGE_DIR / f"{EMOTION_DISPLAY[emotion]}.png"
    if not path.exists():
        return
    data = base64.b64encode(path.read_bytes()).decode()
    print(f"\033]1337;File=inline=1;width=12;preserveAspectRatio=1:{data}\a")

# 2. GPT 모델이 응답할 JSON 구조를 Pydantic 모델로 강제합니다 (Structured Outputs).
class EmotionAnalysisResponse(BaseModel):
    primary_emotion: Emotion      # 가장 주된 감정
    secondary_emotion: Emotion    # 부가적인 감정
    confidence_score: float         # 판독 신뢰도 (0.0 ~ 1.0)
    intensity: int                  # 감정의 강도 (1 ~ 9)
    advice: str | None              # 부정적인 감정이 강할 때의 대응 코멘트 (해당 없으면 None)

# 부정적인 감정: 주 감정이 이 중 하나이고 강도가 ADVICE_MIN_INTENSITY 이상이면 대응 코멘트를 받습니다.
NEGATIVE_EMOTIONS = [Emotion.FEAR, Emotion.SADNESS, Emotion.DISGUST, Emotion.ANGER]
ADVICE_MIN_INTENSITY = 7

# 감성사전 근거단어 방식: 평가(1,200문장)에서 가장 정확했던 구성으로, 앱도 이 방식으로 판독합니다.
RULE_EVIDENCE = """
입력에 감성사전 [참고] 섹션이 있으면 그 단어들 중 실제로 화자의 감정을 드러내는 단어만 골라 evidence_words에 넣는다.
- 문맥상 감정과 무관하거나 뜻이 다르게 쓰인 단어(동음이의어, 부정, 반어, 대상 묘사)는 넣지 않는다.
- 해당하는 단어가 없으면 빈 목록으로 둔다.
- primary_emotion은 evidence_words와 문장 전체 맥락을 함께 보고 정한다."""

# 방식 3 응답: 근거 단어를 먼저 고르고 나서 감정을 판단하도록 evidence_words를 맨 앞에 둡니다.
class EvidenceResponse(BaseModel):
    evidence_words: list[str]
    primary_emotion: Emotion
    secondary_emotion: Emotion
    confidence_score: float
    intensity: int
    advice: str | None

SYSTEM_PROMPT = """너는 한국어 문장에 담긴 감정을 판독한다.

아래 8가지 기본 감정 중 가장 두드러진 감정을 primary_emotion으로, 함께 나타나는 감정을 secondary_emotion으로 고른다. 두 감정은 반드시 서로 달라야 한다.
{criteria}

부정적인 문장은 바로 슬픔으로 고르지 말고 다음 순서로 판단한다.
1. 탓하거나 따지는 대상이 있는가? 다른 사람·상황뿐 아니라 자기 자신을 탓하거나 한심해하는 것도 분노 (대상 자체를 멀리하고 싶으면 혐오)
2. 걱정·고민·스트레스·난감함·혼란처럼 앞으로 어떻게 될지, 어떻게 해야 할지 몰라 마음이 불편한가? 공포
3. 이미 잃었거나 끝나서 어쩔 수 없이 가라앉고 체념했는가? 슬픔

intensity는 primary_emotion의 강도이며 1~9 정수로 답한다.
{intensity}

confidence_score는 primary_emotion 판단에 대한 확신도로 0.0~1.0 사이 값으로 답한다.

advice: primary_emotion이 부정적인 감정({negative}) 중 하나이고 intensity가 {min_intensity} 이상이면, 이 감정을 느끼는 사람이 지금 해볼 수 있는 대응 방법을 1~2문장의 따뜻한 한국어 존댓말로 쓴다. 그 외에는 null로 둔다.

입력에 신조어 용례 [참고] 섹션이 있으면 신조어의 뜻을 이해하는 데만 쓰고, 감정 판단 대상으로 삼지 않는다.
{extra_rules}"""

# Jev(비교 실험)와 GPT 모델이 8가지 기본 감정을 정확히 분류할 수 있도록 각 감정의 의미(기준)를 딕셔너리로 정의합니다.
# 플루치크 감정의 바퀴의 강도 3단계(약함 - 기본 - 강함, 나무위키 '로버트 플루치크' 표기)와
# 각 감정이 이끄는 행동 경향을 함께 적어, 약하거나 강한 형태의 감정도 같은 기본 감정으로 묶이게 합니다.
EMOTION_CRITERIA = {
    Emotion.JOY.value: (
        "평안 - 기쁨 - 황홀. 이미 일어난 좋은 일이나 지금의 상황 때문에 스스로 즐겁고 만족스러움. "
        "초점은 '나의 기분'. "
        "(아직 일어나지 않은 일을 바라면 기대, 특정 대상을 믿고 높이 평가하면 신뢰)"
    ),
    Emotion.TRUST.value: (
        "승인 - 신뢰 - 존경. 특정 사람·집단·대상을 믿을 만하고 훌륭하다고 평가함. "
        "인정, 의지, 고마움, 존경, 응원. 초점은 '대상에 대한 평가'. "
        "사람·작품의 능력이나 매력에 대한 감탄·찬사(천재, 명곡, 명문, 레전드, 납득, 역시)는 ㅠㅠ나 감탄 부호가 붙어도 신뢰. "
        "(예상 밖이라 놀라워하기만 하면 놀람, 결과가 좋아 즐거우면 기쁨)"
    ),
    Emotion.FEAR.value: (
        "불안 - 공포 - 극심한 공포. 아직 일어나지 않았거나 진행 중인 위협·나쁜 일을 걱정하며 피하고 싶음. "
        "걱정, 초조, 두려움, 겁, 고민, 스트레스, 난감함, 혼란. 건강·노후·진로·돈처럼 앞날이 불확실해 마음이 불편함. "
        "시점은 '앞으로' 또는 '아직 해결되지 않은 지금'. "
        "(이미 잃고 가라앉은 상태면 슬픔, 위협을 준 대상을 탓하면 분노)"
    ),
    Emotion.SURPRISE.value: (
        "신경쓰임 - 놀람 - 깜짝 놀람. 예상과 다른 일이 갑자기 일어나 어리둥절하거나 믿기지 않음. "
        "핵심은 '의외성' 자체. "
        "(대상을 높이 평가하는 감탄은 신뢰, 어이없어하며 비난하면 분노나 혐오)"
    ),
    Emotion.SADNESS.value: (
        "수심 - 슬픔 - 비탄. 이미 무언가를 잃거나 실패해서 마음이 가라앉고 기운이 빠짐. "
        "상실, 그리움, 후회, 외로움, 체념, 무력감. 탓할 대상이 없거나 원망보다 체념이 앞섬. "
        "(누군가나 자기 자신을 탓하면 분노, 앞날이나 해결되지 않은 문제가 걱정이면 공포. 부정적이라는 이유만으로 고르지 않음)"
    ),
    Emotion.DISGUST.value: (
        "지루함 - 혐오 - 증오. 대상 자체가 싫고 역겹거나 질려서 멀리하고 싶음. "
        "불쾌감, 경멸, 질림. 초점은 '거리를 두고 싶음'. "
        "(따지고 맞서려 하면 분노)"
    ),
    Emotion.ANGER.value: (
        "짜증 - 분노 - 격노. 누군가의 행동이나 상황이 부당하다고 느껴 화가 남. "
        "원망, 억울함, 짜증, 불만, 비난. 탓하는 대상이 있고 따지거나 바로잡고 싶음. "
        "억울함·서운함이 슬픈 어조로 표현되어도 탓하는 대상이 있으면 분노. "
        "자기 자신에 대한 자책·한심함도 분노"
    ),
    Emotion.ANTICIPATION.value: (
        "관심 - 기대 - 경계. 아직 일어나지 않은 일에 주의를 두고 기다리거나 준비함. "
        "설렘, 바람, 계획, 궁금함, 대비, 다짐. 상대에게 바라는 인사·소망(잘 자, 좋은 꿈 꿔, ~하길, ~해주셨으면)도 기대. "
        "시점은 '앞으로'. "
        "(이미 이루어져 즐거우면 기쁨, 나쁜 결과를 두려워하면 공포)"
    ),
}

INTENSITY_CRITERIA = [
    "1점: 감정이 아주 희미하게 느껴짐",
    "2점: 감정이 약하게 느껴짐",
    "3점: 감정이 조금 느껴짐",
    "4점: 감정이 어느 정도 느껴짐",
    "5점: 감정이 뚜렷하고 일반적인 수준으로 느껴짐",
    "6점: 감정이 꽤 강하게 느껴짐",
    "7점: 감정이 강하게 느껴짐 (행동에 영향을 줄 정도)",
    "8점: 감정이 매우 강하게 느껴짐 (이성적 판단이 흐려질 정도)",
    "9점: 감정이 통제하기 힘들 정도로 극도로 강렬함"
]

# 3. GPT API 호출 함수
def analyze_emotion_with_gpt(input_text: str, neologisms: list[str], extra_rules: str = "", extra_reference: str = "",
                             text_format: type[BaseModel] = EmotionAnalysisResponse, model: str = "gpt-4.1",
                             return_usage: bool = False) -> EmotionAnalysisResponse:
    load_dotenv()

    system_prompt = SYSTEM_PROMPT.format(
        criteria="\n".join(f"- {name}: {meaning}" for name, meaning in EMOTION_CRITERIA.items()),
        intensity="\n".join(INTENSITY_CRITERIA),
        negative=", ".join(emotion.value for emotion in NEGATIVE_EMOTIONS),
        min_intensity=ADVICE_MIN_INTENSITY,
        extra_rules=extra_rules,
    )

    client = OpenAI()
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_state(input_text, neologisms, extra_reference)},
        ],
        text_format=text_format,
    )
    # return_usage=True면 비용 비교용으로 토큰 사용량을 함께 돌려줍니다.
    if return_usage:
        return response.output_parsed, response.usage
    return response.output_parsed

# 4. 프로그램 실행의 진입점이 되는 main 함수
def main():
    customer_review = input("입력: ")
    
    
    # 신조어 탐지 후 API 호출 및 결과 받아오기
    neologisms = find_neologisms(customer_review)
    words = find_sentiment_words(customer_review)
    reference = sentiment_reference(words) if words else ""
    analysis = analyze_emotion_with_gpt(customer_review, neologisms, RULE_EVIDENCE, reference, EvidenceResponse)
        
    primary_name = EMOTION_DISPLAY[analysis.primary_emotion]
    secondary_name = EMOTION_DISPLAY[analysis.secondary_emotion]
    intensity_bar = "🟧" * analysis.intensity + "⬜" * (9 - analysis.intensity)

    print("\n[분석 완료]")
    if neologisms:
        print(f"신조어: {', '.join(neologisms)}")
    if words and analysis.evidence_words:  # 감성사전이 없으면 모델이 근거 단어를 지어낼 수 있어 표시하지 않음
        print(f"근거 단어: {', '.join(analysis.evidence_words)}")
    print_emotion_image(analysis.primary_emotion)
    print(f"주 감정: {primary_name}")
    print_emotion_image(analysis.secondary_emotion)
    print(f"부 감정: {secondary_name}")
    composite = COMPOSITE_EMOTIONS.get(frozenset({analysis.primary_emotion, analysis.secondary_emotion}))
    if composite:  # 두 감정이 같게 나오면 합성 감정이 없음
        print(f"합성 감정: {composite} ({primary_name} + {secondary_name})")
    print(f"강도:   {intensity_bar} ({analysis.intensity}/9)")
    print(f"신뢰도: {analysis.confidence_score:.0%}")
    if analysis.advice:
        print(f"\n[대응 코멘트]\n{analysis.advice}")

if __name__ == "__main__":
    main()
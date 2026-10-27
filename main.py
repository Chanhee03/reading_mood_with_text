import base64
import json
import readline  # input()에서 한글을 백스페이스로 지울 때 바이트가 남지 않도록 글자 단위 편집 사용
import sys
from enum import Enum
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# 1. 26가지 기본 감정을 고정된 값(Enum)으로 정의합니다.
class Emotion26(str, Enum):
    ADMIRATION = "ADMIRATION"                   # 존경
    ADORATION = "ADORATION"                     # 흠모
    AESTHETIC_APPRECIATION = "AESTHETIC_APPRECIATION" # 심미적 감상
    AMUSEMENT = "AMUSEMENT"                     # 즐거움
    ANXIETY = "ANXIETY"                         # 걱정
    AWE = "AWE"                                 # 경외감
    AWKWARDNESS = "AWKWARDNESS"                 # 어색함
    BOREDOM = "BOREDOM"                         # 지루함
    CALMNESS = "CALMNESS"                       # 차분함
    CONFUSION = "CONFUSION"                     # 혼란스러움
    CRAVING = "CRAVING"                         # 간절함
    DISGUST = "DISGUST"                         # 역겨움
    EMPATHETIC_PAIN = "EMPATHETIC_PAIN"         # 공감적 고통
    ENTRANCEMENT = "ENTRANCEMENT"               # 황홀경
    ENVY = "ENVY"                               # 부러움, 질투
    EXCITEMENT = "EXCITEMENT"                   # 흥분됨, 신남
    FEAR = "FEAR"                               # 두려움
    HORROR = "HORROR"                           # 공포
    INTEREST = "INTEREST"                       # 흥미, 호기심
    JOY = "JOY"                                 # 기쁨
    NOSTALGIA = "NOSTALGIA"                     # 향수, 그리움
    ROMANCE = "ROMANCE"                         # 로맨스
    SADNESS = "SADNESS"                         # 슬픔
    SATISFACTION = "SATISFACTION"               # 만족
    SYMPATHY = "SYMPATHY"                       # 공감
    TRIUMPH = "TRIUMPH"                         # 승리감

# 출력용: 감정별 한글 이름
EMOTION_DISPLAY = {
    Emotion26.ADMIRATION: "존경",
    Emotion26.ADORATION: "흠모",
    Emotion26.AESTHETIC_APPRECIATION: "심미적 감상",
    Emotion26.AMUSEMENT: "즐거움",
    Emotion26.ANXIETY: "걱정",
    Emotion26.AWE: "경외감",
    Emotion26.AWKWARDNESS: "어색함",
    Emotion26.BOREDOM: "지루함",
    Emotion26.CALMNESS: "차분함",
    Emotion26.CONFUSION: "혼란스러움",
    Emotion26.CRAVING: "간절함",
    Emotion26.DISGUST: "역겨움",
    Emotion26.EMPATHETIC_PAIN: "공감적 고통",
    Emotion26.ENTRANCEMENT: "황홀경",
    Emotion26.ENVY: "부러움, 질투",
    Emotion26.EXCITEMENT: "흥분됨, 신남",
    Emotion26.FEAR: "두려움",
    Emotion26.HORROR: "공포",
    Emotion26.INTEREST: "흥미, 호기심",
    Emotion26.JOY: "기쁨",
    Emotion26.NOSTALGIA: "향수, 그리움",
    Emotion26.ROMANCE: "로맨스",
    Emotion26.SADNESS: "슬픔",
    Emotion26.SATISFACTION: "만족",
    Emotion26.SYMPATHY: "공감",
    Emotion26.TRIUMPH: "승리감",
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

def build_state(text: str, neologisms: list[str]) -> str:
    # 신조어가 있으면 용례를 참고 자료로 덧붙여 모델이 뜻을 파악할 수 있게 합니다.
    if not neologisms:
        return text
    lines = ["[분석할 문장]", text, "", "[참고: 위 문장에 쓰인 신조어의 용례. 감정 판단 대상이 아니며 신조어의 뜻을 이해하는 데만 사용]"]
    for word in neologisms:
        for question, answer in NEOLOGISMS[word]:
            lines.append(f"- {word}: \"{question}\" / \"{answer}\"")
    return "\n".join(lines)

def print_emotion_image(emotion: Emotion26):
    # iTerm2 인라인 이미지 프로토콜로 출력 (JOY처럼 이미지가 없으면 생략)
    path = EMOTION_IMAGE_DIR / f"{emotion.value}.png"
    if not path.exists():
        return
    data = base64.b64encode(path.read_bytes()).decode()
    print(f"\033]1337;File=inline=1;width=12;preserveAspectRatio=1:{data}\a")

# 2. GPT 모델이 응답할 JSON 구조를 Pydantic 모델로 강제합니다 (Structured Outputs).
class EmotionAnalysisResponse(BaseModel):
    primary_emotion: Emotion26      # 가장 주된 감정
    secondary_emotion: Emotion26    # 부가적인 감정
    confidence_score: float         # 판독 신뢰도 (0.0 ~ 1.0)
    intensity: int                  # 감정의 강도 (1 ~ 9)
    advice: str | None              # 부정적인 감정이 강할 때의 대응 코멘트 (해당 없으면 None)

# 부정적인 감정: 주 감정이 이 중 하나이고 강도가 ADVICE_MIN_INTENSITY 이상이면 대응 코멘트를 받습니다.
NEGATIVE_EMOTIONS = [
    Emotion26.ANXIETY, Emotion26.AWKWARDNESS, Emotion26.BOREDOM, Emotion26.CONFUSION,
    Emotion26.DISGUST, Emotion26.EMPATHETIC_PAIN, Emotion26.ENVY, Emotion26.FEAR,
    Emotion26.HORROR, Emotion26.SADNESS,
]
ADVICE_MIN_INTENSITY = 7

SYSTEM_PROMPT = """너는 한국어 문장에 담긴 감정을 판독한다.

아래 26가지 감정 중 가장 두드러진 감정을 primary_emotion으로, 함께 나타나는 감정을 secondary_emotion으로 고른다. 두 감정은 반드시 서로 달라야 한다.
{criteria}

intensity는 primary_emotion의 강도이며 1~9 정수로 답한다.
{intensity}

confidence_score는 primary_emotion 판단에 대한 확신도로 0.0~1.0 사이 값으로 답한다.

advice: primary_emotion이 부정적인 감정({negative}) 중 하나이고 intensity가 {min_intensity} 이상이면, 이 감정을 느끼는 사람이 지금 해볼 수 있는 대응 방법을 2~3문장의 따뜻한 한국어 존댓말로 쓴다. 그 외에는 null로 둔다.

입력에 [참고] 섹션이 있으면 신조어의 뜻을 이해하는 데만 쓰고, 감정 판단 대상으로 삼지 않는다."""

# 3. GPT API 호출 함수
def analyze_emotion_with_gpt(input_text: str, neologisms: list[str]) -> EmotionAnalysisResponse:
    load_dotenv()

    # 모델이 26가지 감정을 정확히 분류할 수 있도록 각 감정의 의미(기준)를 딕셔너리로 정의합니다.
    emotion_criteria = {
        Emotion26.ADMIRATION.value: "존경하거나 우러러보는 감정",
        Emotion26.ADORATION.value: "깊이 흠모하거나 애정을 느끼는 감정",
        Emotion26.AESTHETIC_APPRECIATION.value: "예술이나 아름다움을 감상하는 감정",
        Emotion26.AMUSEMENT.value: "재미있거나 즐거운 감정",
        Emotion26.ANXIETY.value: "걱정, 불안, 초조함",
        Emotion26.AWE.value: "경외감, 압도되는 느낌",
        Emotion26.AWKWARDNESS.value: "어색하고 민망한 감정",
        Emotion26.BOREDOM.value: "지루함, 따분함",
        Emotion26.CALMNESS.value: "차분하고 평온한 상태",
        Emotion26.CONFUSION.value: "혼란스럽거나 당혹스러운 감정",
        Emotion26.CRAVING.value: "무언가를 간절히 원하거나 갈망함",
        Emotion26.DISGUST.value: "역겨움, 혐오감, 강한 불쾌감",
        Emotion26.EMPATHETIC_PAIN.value: "타인의 고통에 공감하여 느끼는 아픔",
        Emotion26.ENTRANCEMENT.value: "무언가에 매료된 황홀경",
        Emotion26.ENVY.value: "부러움이나 질투",
        Emotion26.EXCITEMENT.value: "흥분되고 신나는 감정",
        Emotion26.FEAR.value: "두려움, 무서움",
        Emotion26.HORROR.value: "소름 끼치는 공포",
        Emotion26.INTEREST.value: "흥미, 호기심, 관심",
        Emotion26.JOY.value: "기쁨, 행복함",
        Emotion26.NOSTALGIA.value: "과거에 대한 향수나 그리움",
        Emotion26.ROMANCE.value: "로맨틱한 감정",
        Emotion26.SADNESS.value: "슬픔, 우울함",
        Emotion26.SATISFACTION.value: "만족스러움",
        Emotion26.SYMPATHY.value: "타인에 대한 동정이나 공감",
        Emotion26.TRIUMPH.value: "승리감, 성취감"
    }

    intensity_criteria = [
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

    system_prompt = SYSTEM_PROMPT.format(
        criteria="\n".join(f"- {name}: {meaning}" for name, meaning in emotion_criteria.items()),
        intensity="\n".join(intensity_criteria),
        negative=", ".join(emotion.value for emotion in NEGATIVE_EMOTIONS),
        min_intensity=ADVICE_MIN_INTENSITY,
    )

    client = OpenAI()
    response = client.responses.parse(
        model="gpt-4.1",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_state(input_text, neologisms)},
        ],
        text_format=EmotionAnalysisResponse,
    )
    return response.output_parsed

# 4. 프로그램 실행의 진입점이 되는 main 함수
def main():
    customer_review = input("입력: ")
    
    
    # 신조어 탐지 후 API 호출 및 결과 받아오기
    neologisms = find_neologisms(customer_review)
    analysis = analyze_emotion_with_gpt(customer_review, neologisms)
        
    primary_name = EMOTION_DISPLAY[analysis.primary_emotion]
    secondary_name = EMOTION_DISPLAY[analysis.secondary_emotion]
    intensity_bar = "🟧" * analysis.intensity + "⬜" * (9 - analysis.intensity)

    print("\n[분석 완료]")
    if neologisms:
        print(f"신조어: {', '.join(neologisms)}")
    print_emotion_image(analysis.primary_emotion)
    print(f"주 감정: {primary_name}")
    print_emotion_image(analysis.secondary_emotion)
    print(f"부 감정: {secondary_name}")
    print(f"강도:   {intensity_bar} ({analysis.intensity}/9)")
    print(f"신뢰도: {analysis.confidence_score:.0%}")
    if analysis.advice:
        print(f"\n[대응 코멘트]\n{analysis.advice}")

if __name__ == "__main__":
    main()
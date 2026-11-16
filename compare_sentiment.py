# 감성사전을 프롬프트에 넣는 방식 3가지와 Jev 1차 분류 방식을 기존 방식과 나란히 비교하는 실험 스크립트입니다.
# 사용법:
#   python compare_sentiment.py                  # 아래 TEST_SENTENCES로 비교 (gpt-4.1)
#   python compare_sentiment.py "문장1" "문장2"   # 직접 입력한 문장으로 비교
#   python compare_sentiment.py --models gpt-4.1,gpt-4.1-mini   # 여러 모델로 비교 (쉼표로 구분)
#   python compare_sentiment.py --eval data/eval_set.json       # 정답 라벨 파일로 정확도까지 비교
#   python compare_sentiment.py --variants "기존,Jev→LLM,Jev 단독"  # 일부 방식만 비교
#   python compare_sentiment.py --eval data/eval_external.json --save results/run.jsonl
#       # 호출마다 결과(판독 결과, Jev 확률, 토큰, 비용 등)를 JSONL에 바로 저장. 같은 명령을 다시 실행하면 끝난 호출은 건너뛰고
#       # 실패·미완료 호출만 이어서 돌립니다. 실행 설정(프롬프트, 가격표, 평가 파일 해시)은 run.meta.json에 남깁니다.
# 정답 라벨 파일 형식: [{"text": "문장", "label": "분노 / 서운함", "primary": ["DISGUST"], "secondary": ["SADNESS"], "advice": true}, ...]
#   primary = 정답으로 인정할 주 감정 목록, secondary = 보조 감정 목록 (느슨한 정답률에 사용)
#   label = 원래 라벨 표시용, advice = 대응 코멘트가 붙어야 하는지. secondary/label/advice는 생략 가능
#   외부 말뭉치로 만든 평가 파일: python build_eval_set.py → --eval data/eval_external.json
# 실행 전 `pip install kiwipiepy`와 `python build_sentiment.py`가 필요합니다.
import argparse
import hashlib
import json
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from dotenv import load_dotenv
from pydantic import BaseModel
from typesafe_sdk import Choice, Score, TypeSafeClient

from main import (ADVICE_MIN_INTENSITY, BASE_DIR, EMOTION_CRITERIA, EMOTION_DISPLAY, INTENSITY_CRITERIA,
                  NEGATIVE_EMOTIONS, RULE_EVIDENCE, SENTIMENT, SYSTEM_PROMPT, Emotion, EmotionAnalysisResponse,
                  EvidenceResponse, analyze_emotion_with_gpt, build_state, find_neologisms, find_sentiment_words,
                  sentiment_reference)

# 사전 점수만 보면 틀리기 쉬운 문장(부정어, 반어, 관용 표현, 대상 묘사)을 섞어 두었습니다.
TEST_SENTENCES = [
    "너무 슬퍼서 하루 종일 눈물이 났어",
    "시험 망쳐서 진짜 우울하고 불안하다",
    "이 집 떡볶이 죽을 만큼 맛있다",
    "솔직히 하나도 안 슬퍼",
    "와 진짜 행복하다~ 월요일부터 야근이라니",
    "살인자가 나오는 영화 봤는데 반전이 대박이라 재밌었어",
    "친구가 아프다는 소식 듣고 마음이 너무 아팠다",
    "합격 발표 보고 소리 질렀어 드디어 해냈다",
    "내일 발표인데 망하면 어떡하지",
    "그냥 오늘은 평범한 하루였어",
]

# ---------------------------------------------------------------- 비교할 방식들

RULE_POLARITY = """
입력에 감성사전 [참고] 섹션이 있으면 단어의 사전적 긍·부정 극성 힌트로만 쓴다.
- primary_emotion이 긍정 계열인지 부정 계열인지 판단할 때만 보조로 쓴다.
- 감정의 종류와 intensity는 이 점수로 정하지 않는다.
- 부정어(안, 못), 반어, 비꼼, 관용 표현("죽을 만큼 맛있다")이 있으면 점수를 무시하고 문맥을 따른다."""

RULE_INTENSITY = """
입력에 감성사전 [참고] 섹션이 있으면 intensity를 정할 때 참고한다. (4~5점은 중립)
- 1·2점이나 7점 단어가 감정의 주체에게 직접 쓰였다면 강도를 높게 볼 근거가 된다.
- 3·6점 단어만 있으면 강도를 과하게 올리지 않는다.
- 단어가 감정 주체가 아닌 대상·사건을 묘사할 때(예: "살인자가 나오는 영화 봤는데 재밌었어")는 강도 판단에서 제외한다.
- 감정의 종류는 이 점수로 정하지 않는다."""

RULE_JEV = """
입력에 Jev [참고] 섹션이 있으면 별도 감정 분류 모델(Jev)의 1차 분류 결과로 참고한다.
- 확률이 높고 문장의 문맥과 맞으면 따른다.
- 반어, 부정, 관용 표현 등으로 문맥과 맞지 않으면 문장에 대한 너의 판단을 우선한다."""

# ---------------------------------------------------------------- Jev

JEV_MODEL = "jev-latest"

def classify_with_jev(text: str, neologisms: list[str]):
    # 예전 main.py(커밋 a0a4a47)와 같은 방식: 감정 Choice 하나의 확률 1·2위를 주/부 감정으로, 강도는 Score로 받습니다.
    load_dotenv()
    with TypeSafeClient() as client:
        result = client.system_one(
            model=JEV_MODEL,
            state=build_state(text, neologisms),
            questions={"emotion": Choice(criteria=EMOTION_CRITERIA), "intensity": Score(criteria=INTENSITY_CRITERIA)},
        )
    emotion = result.answers["emotion"]
    ranked = sorted(emotion.probabilities, key=emotion.probabilities.get, reverse=True)
    intensity = result.answers["intensity"].score
    parsed = EmotionAnalysisResponse(
        primary_emotion=ranked[0], secondary_emotion=ranked[1], confidence_score=emotion.confidence,
        intensity=int(round(intensity)), advice=None,
    )
    reference = "\n".join([
        "[참고: Jev 1차 감정 분류 결과]",
        "- 확률 상위 3개: " + ", ".join(f"{name} {emotion.probabilities[name]:.2f}" for name in ranked[:3]),
        f"- 강도 추정: {intensity:.1f} (1~9)",
    ])
    # 저장용: Jev가 낸 값 전체 (확률 8개, 신뢰도, 강도, 토큰)
    info = {"probabilities": dict(emotion.probabilities), "confidence": emotion.confidence, "intensity": intensity,
            "input_tokens": result.usage.input_tokens or 0, "output_tokens": result.usage.output_tokens or 0}
    return parsed, result.usage, reference, info

# ---------------------------------------------------------------- 비용

# 1M 토큰당 가격 (USD): 입력, 캐시된 입력, 출력. 2026-11-04 기준 https://developers.openai.com/api/docs/pricing
# gpt-5.6-sol은 2026-11-21까지 프로모션 가격입니다. 표에 없는 모델은 토큰 수만 보여줍니다.
PRICES = {
    "gpt-4.1": (2.00, 0.50, 8.00),
    "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
}
# Jev: 입력 1M 토큰당 $0.042, 출력 무료. 공식 가격 페이지가 없어 2026-11 기준 보도된 출시 가격을 씁니다.
JEV_INPUT_PRICE = 0.042

def openai_cost(model: str, usage) -> float | None:
    if model not in PRICES:
        return None
    input_price, cached_price, output_price = PRICES[model]
    cached = usage.input_tokens_details.cached_tokens
    return ((usage.input_tokens - cached) * input_price + cached * cached_price
            + usage.output_tokens * output_price) / 1_000_000

def jev_cost(usage) -> float:
    return (usage.input_tokens or 0) * JEV_INPUT_PRICE / 1_000_000

# ---------------------------------------------------------------- 실행

@dataclass
class Run:
    result: BaseModel
    seconds: float          # Jev→LLM은 Jev + LLM 호출 시간 합계
    cost: float | None      # USD, 가격 정보가 없으면 None
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cached_tokens: int = 0
    jev: dict | None = None     # Jev를 거친 방식이면 classify_with_jev의 info
    inputs: dict | None = None  # LLM에 넘긴 참고 자료 (신조어, 감성사전 단어, reference 원문)

    @property
    def advice(self) -> bool:
        return self.result.advice is not None

def text_format_of(variant: str) -> type[BaseModel]:
    return EvidenceResponse if variant in ("3 근거단어", "Jev+근거단어→LLM") else EmotionAnalysisResponse

def to_record(text: str, model: str, variant: str, run_: Run, label: dict | None) -> dict:
    return {"text": text, "model": model, "variant": variant, "label": label,
            "result": run_.result.model_dump(mode="json"), "seconds": run_.seconds, "cost": run_.cost,
            "input_tokens": run_.input_tokens, "cached_tokens": run_.cached_tokens,
            "output_tokens": run_.output_tokens, "reasoning_tokens": run_.reasoning_tokens,
            "jev": run_.jev, "inputs": run_.inputs}

def from_record(record: dict) -> Run:
    return Run(text_format_of(record["variant"]).model_validate(record["result"]), record["seconds"], record["cost"],
               record["input_tokens"], record["output_tokens"], record["reasoning_tokens"],
               record["cached_tokens"], record["jev"], record["inputs"])

def run(variant: str, text: str, model: str) -> Run:
    start = time.perf_counter()
    neologisms = find_neologisms(text)
    if variant == "Jev 단독":
        parsed, usage, _, jev_info = classify_with_jev(text, neologisms)
        # Jev는 코멘트를 쓰지 못하므로, 앱과 같은 규칙(부정 감정 + 강도 7 이상)으로 코멘트 대상 여부만 표시합니다.
        advice = parsed.primary_emotion in NEGATIVE_EMOTIONS and parsed.intensity >= ADVICE_MIN_INTENSITY
        parsed = parsed.model_copy(update={"advice": "(규칙상 코멘트 대상)" if advice else None})
        return Run(parsed, time.perf_counter() - start, jev_cost(usage), usage.input_tokens or 0, usage.output_tokens or 0, 0,
                   jev=jev_info, inputs={"neologisms": neologisms})

    jev_usage = jev_info = None
    words = []
    if variant == "Jev→LLM":
        _, jev_usage, reference, jev_info = classify_with_jev(text, neologisms)
        rule, text_format = RULE_JEV, EmotionAnalysisResponse
    elif variant in JEV_SENTIMENT_RULES:
        # Jev 1차 분류와 감성사전(방식별 규칙)을 함께 넘깁니다.
        _, jev_usage, reference, jev_info = classify_with_jev(text, neologisms)
        words = find_sentiment_words(text)
        if words:
            reference += "\n\n" + sentiment_reference(words)
        rule = RULE_JEV + "\n" + JEV_SENTIMENT_RULES[variant]
        text_format = EvidenceResponse if variant == "Jev+근거단어→LLM" else EmotionAnalysisResponse
    elif variant == "기존":
        reference, rule, text_format = "", "", EmotionAnalysisResponse
    else:
        words = find_sentiment_words(text)
        reference = sentiment_reference(words) if words else ""
        rule = {"1 극성힌트": RULE_POLARITY, "2 강도보정": RULE_INTENSITY, "3 근거단어": RULE_EVIDENCE}[variant]
        text_format = EvidenceResponse if variant == "3 근거단어" else EmotionAnalysisResponse

    parsed, usage = analyze_emotion_with_gpt(text, neologisms, rule, reference, text_format, model=model, return_usage=True)
    cost = openai_cost(model, usage)
    if cost is not None and jev_usage is not None:
        cost += jev_cost(jev_usage)
    return Run(parsed, time.perf_counter() - start, cost, usage.input_tokens, usage.output_tokens,
               usage.output_tokens_details.reasoning_tokens, usage.input_tokens_details.cached_tokens,
               jev_info, {"neologisms": neologisms, "sentiment_words": words, "reference": reference})

JEV_SENTIMENT_RULES = {"Jev+극성힌트→LLM": RULE_POLARITY, "Jev+강도보정→LLM": RULE_INTENSITY, "Jev+근거단어→LLM": RULE_EVIDENCE}
LLM_VARIANTS = ["기존", "1 극성힌트", "2 강도보정", "3 근거단어", "Jev→LLM", *JEV_SENTIMENT_RULES]
VARIANTS = LLM_VARIANTS + ["Jev 단독"]  # Jev 단독은 LLM 모델과 무관해 한 번만 돌립니다.

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sentences", nargs="*")
    parser.add_argument("--models", default="gpt-4.1", help="비교할 모델 (쉼표로 구분)")
    parser.add_argument("--variants", default=",".join(VARIANTS), help="비교할 방식 (쉼표로 구분)")
    parser.add_argument("--eval", help="정답 라벨 JSON 파일")
    parser.add_argument("--save", help="호출별 결과를 저장·이어받을 JSONL 파일")
    args = parser.parse_args()
    if not SENTIMENT and any(v != "기존" and v != "Jev→LLM" and v != "Jev 단독" for v in args.variants.split(",")):
        parser.error("감성사전을 쓰는 방식에는 data/sentiment.json이 필요합니다 (python build_sentiment.py)")

    labels = {}
    if args.eval:
        items = json.loads(open(args.eval, encoding="utf-8").read())
        labels = {item["text"]: item for item in items}
        sentences = list(labels)
    else:
        sentences = args.sentences or TEST_SENTENCES
    models = args.models.split(",")
    variants = args.variants.split(",")

    # 행 = (모델, 방식). Jev 단독은 모델 자리에 Jev 모델 이름을 씁니다.
    rows = [(model, variant) for model in models for variant in variants if variant in LLM_VARIANTS]
    if "Jev 단독" in variants:
        rows.append((JEV_MODEL, "Jev 단독"))
    jobs = [(text, model, variant) for text in sentences for model, variant in rows]
    results = {}
    save = Path(args.save) if args.save else None
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        if save.exists():
            for line in save.read_text().splitlines():
                record = json.loads(line)
                if "error" not in record:
                    results[(record["text"], record["model"], record["variant"])] = from_record(record)
            print(f"이어받기: {save}에서 끝난 호출 {len(results)}개를 건너뜁니다.")
        write_meta(save, args, models, variants, rows, len(sentences))
    lock = threading.Lock()

    def job_fn(job):
        text, model, variant = job
        for attempt in range(3):
            try:
                run_ = run(variant, text, model)
                record = to_record(text, model, variant, run_, labels.get(text))
                break
            except Exception as error:  # API 오류는 잠시 쉬었다 다시 시도하고, 끝내 실패하면 기록만 남깁니다.
                if attempt == 2:
                    run_, record = None, {"text": text, "model": model, "variant": variant, "error": repr(error)}
                time.sleep(2 ** attempt)
        if save:
            with lock, save.open("a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return run_

    todo = [job for job in jobs if job not in results]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results.update(zip(todo, pool.map(job_fn, todo)))
    failed = [job for job in jobs if results.get(job) is None]
    if failed:
        print(f"\n[실패] {len(failed)}개 호출이 3번 시도 후에도 실패했습니다. 같은 명령을 다시 실행하면 이어서 돌립니다.")

    for text in sentences:
        words = find_sentiment_words(text)
        print(f"\n■ {text}")
        if text in labels:
            label = labels[text]
            answer = "/".join(EMOTION_DISPLAY[Emotion(e)] for e in label["primary"])
            original = f"{label['label']} → " if "label" in label else ""
            print(f"  정답: {original}{answer}" + (f" | 코멘트 {'O' if label['advice'] else '-'}" if "advice" in label else ""))
        print(f"  사전 매칭: {', '.join(f'{w}({SENTIMENT[w][0][0]})' for w in words) or '없음'}")
        for model, variant in rows:
            run_ = results.get((text, model, variant))
            if run_ is None:
                print(f"  {model} · {variant:<7} | 실패")
                continue
            r = run_.result
            mark = ""
            if text in labels:
                mark = " ✓" if r.primary_emotion.value in labels[text]["primary"] else " ✗"
            line = (f"  {model} · {variant:<7} | {EMOTION_DISPLAY[r.primary_emotion]}{mark} / {EMOTION_DISPLAY[r.secondary_emotion]}"
                    f" | 강도 {r.intensity} | 신뢰도 {r.confidence_score:.0%} | 코멘트 {'O' if run_.advice else '-'}"
                    f" | {run_.seconds:.1f}s")
            if isinstance(r, EvidenceResponse):
                line += f" | 근거: {', '.join(r.evidence_words) or '없음'}"
            print(line)

    # 요약: 출력 토큰에는 GPT-5 계열의 추론(reasoning) 토큰이 포함됩니다.
    # 지연 시간은 동시에 4개씩 호출한 상태에서 잰 값이라 단독 호출보다 조금 길 수 있습니다.
    print(f"\n[요약] 문장 {len(sentences)}개 기준")
    header = "  모델 · 방식 | 평균 지연 | 평균 입력 토큰 | 평균 출력 토큰(추론) | 합계 비용 | 1,000회당"
    if labels:
        header += " | 주 감정 정답률 | 느슨한 정답률(주·보조 중 하나) | 코멘트 일치율"
    print(header)
    for model, variant in rows:
        done = [text for text in sentences if results.get((text, model, variant)) is not None]
        runs = [results[(text, model, variant)] for text in done]
        n = len(runs)
        if n == 0:
            continue
        costs = [r.cost for r in runs]
        cost = f"${sum(costs):.4f} | ${sum(costs) / n * 1000:.2f}" if None not in costs else "가격 정보 없음 | -"
        line = (f"  {model} · {variant:<7} | {sum(r.seconds for r in runs) / n:.2f}s"
                f" | {sum(r.input_tokens for r in runs) / n:,.0f}"
                f" | {sum(r.output_tokens for r in runs) / n:,.0f}({sum(r.reasoning_tokens for r in runs) / n:,.0f})"
                f" | {cost}")
        if labels:
            correct = sum(r.result.primary_emotion.value in labels[t]["primary"] for t, r in zip(done, runs))
            graded = [(t, r) for t, r in zip(done, runs) if "advice" in labels[t]]
            advice_ok = sum(r.advice == labels[t]["advice"] for t, r in graded)
            loose = sum(r.result.primary_emotion.value in labels[t]["primary"] + labels[t].get("secondary", [])
                        for t, r in zip(done, runs))
            line += f" | {correct}/{n} ({correct / n:.0%}) | {loose}/{n} ({loose / n:.0%})"
            line += f" | {advice_ok}/{len(graded)} ({advice_ok / len(graded):.0%})" if graded else " | -"
        print(line)

    # 감정별 주 감정 정답률: 정답 라벨의 첫 번째 주 감정 기준으로 묶습니다.
    if labels:
        print("\n[감정별 정답률] 행 = 정답 감정, 오답은 많이 고른 감정 순")
        for model, variant in rows:
            print(f"  {model} · {variant}")
            by_emotion = {}
            for text in sentences:
                run_ = results.get((text, model, variant))
                if run_ is not None:
                    by_emotion.setdefault(labels[text]["primary"][0], []).append((text, run_))
            for emotion, pairs in by_emotion.items():
                ok = sum(r.result.primary_emotion.value in labels[t]["primary"] for t, r in pairs)
                wrong = Counter(EMOTION_DISPLAY[r.result.primary_emotion] for t, r in pairs
                                if r.result.primary_emotion.value not in labels[t]["primary"])
                print(f"    {EMOTION_DISPLAY[Emotion(emotion)]:<3} {ok}/{len(pairs)} ({ok / len(pairs):.0%})"
                      + (f" | 오답: {', '.join(f'{name} {count}' for name, count in wrong.most_common())}" if wrong else ""))

def write_meta(save: Path, args, models, variants, rows, n_sentences):
    # 다시 돌리지 않고도 결과를 해석할 수 있도록 실행 설정을 남깁니다. 이어받을 때는 기존 파일을 보존합니다.
    path = save.with_suffix(".meta.json")
    if path.exists():
        return
    eval_bytes = Path(args.eval).read_bytes() if args.eval else b""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=BASE_DIR).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "main.py", "compare_sentiment.py"], capture_output=True,
                           text=True, cwd=BASE_DIR).stdout.strip()
    meta = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": commit, "uncommitted_changes": dirty.splitlines(),
        "models": models, "variants": variants, "rows": rows, "jev_model": JEV_MODEL,
        "eval_file": args.eval, "eval_sha256": hashlib.sha256(eval_bytes).hexdigest() if args.eval else None,
        "n_sentences": n_sentences,
        "prices_per_1m": PRICES, "jev_input_price_per_1m": JEV_INPUT_PRICE,
        "system_prompt_template": SYSTEM_PROMPT, "emotion_criteria": EMOTION_CRITERIA,
        "intensity_criteria": INTENSITY_CRITERIA, "negative_emotions": [e.value for e in NEGATIVE_EMOTIONS],
        "advice_min_intensity": ADVICE_MIN_INTENSITY,
        "rules": {"jev": RULE_JEV, "polarity": RULE_POLARITY, "intensity": RULE_INTENSITY, "evidence": RULE_EVIDENCE},
    }
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()

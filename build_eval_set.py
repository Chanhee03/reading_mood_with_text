# 외부 말뭉치 두 가지(+ 직접 작성한 문장)로 평가용 정답 라벨 파일을 만듭니다.
# - AI Hub 감성대화말뭉치: 자기 상황과 감정을 1인칭으로 말하는 첫 문장(사람문장1). 일기와 가장 비슷해 기쁨·공포·슬픔·분노에 사용
# - 국립국어원 감정 분석 말뭉치(AI말평 2024): 플루치크 8감정 라벨. 감성대화말뭉치에 없는 신뢰·기대·놀람·혐오에 사용
#   (SNS 글이며 다중 라벨이라, 감정이 하나만 붙은 문장만 씁니다. 정답이 공개되지 않은 test는 제외)
# - data/eval_manual.json (있으면): 직접 작성·라벨링한 문장. 형식은 결과 파일과 같음
# 사용법:
#   python build_eval_set.py                     # 감정당 150개 (부족하면 있는 만큼)
#   python build_eval_set.py --per-emotion 300
#   python build_eval_set.py --per-emotion 40 --seed 1 --exclude data/eval_external.json --output data/eval_dev.json
#       # 프롬프트를 고칠 때 쓰는 개발용 세트. 평가 세트 문장을 빼고 뽑아, 평가 세트에 맞춰 고치는 일을 막습니다.
# 결과: data/eval_external.json → python compare_sentiment.py --eval data/eval_external.json
# 두 말뭉치 모두 재배포가 금지되어 있어 원본 폴더와 결과 파일은 .gitignore에 넣어 두었습니다.
import argparse
import json
import random
from pathlib import Path

import openpyxl

from main import BASE_DIR, Emotion

DIARY_SOURCE = BASE_DIR / "한국어 감정 정보가 포함된 연속적 대화 데이터셋" / "감성대화말뭉치(최종데이터)_Training.xlsx"
NIKL_SOURCES = [BASE_DIR / "NIKL_EA_2024" / f"nikluge-감정분석-2024-{split}.jsonl" for split in ("train", "dev")]
MANUAL = BASE_DIR / "data" / "eval_manual.json"
OUTPUT = BASE_DIR / "data" / "eval_external.json"

# 감성대화말뭉치 감정_대분류 → 플루치크 기본 감정. 상처·당황은 대응하는 기본 감정이 없어 제외합니다.
DIARY_LABEL_MAP = {
    "기쁨": Emotion.JOY,
    "불안": Emotion.FEAR,
    "슬픔": Emotion.SADNESS,
    "분노": Emotion.ANGER,
}
# 국립국어원 말뭉치에서 가져올 감정 (라벨 이름이 Emotion 값의 소문자와 같음)
NIKL_EMOTIONS = [Emotion.TRUST, Emotion.ANTICIPATION, Emotion.SURPRISE, Emotion.DISGUST]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-emotion", type=int, default=150)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--exclude", help="이 파일에 있는 문장은 뽑지 않음 (예: 평가 세트)")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)

    candidates = {emotion: [] for emotion in [*DIARY_LABEL_MAP.values(), *NIKL_EMOTIONS]}
    seen = set()  # compare_sentiment.py가 문장을 키로 쓰므로 같은 문장은 한 번만 넣습니다.
    if args.exclude:
        seen |= {item["text"] for item in json.loads(Path(args.exclude).read_text())}

    # 감성대화말뭉치: F열 감정_대분류, H열 사람문장1
    for row in openpyxl.load_workbook(DIARY_SOURCE, read_only=True).active.iter_rows(min_row=2, values_only=True):
        label, text = row[5], str(row[7] or "").strip()
        if label not in DIARY_LABEL_MAP or text in seen:
            continue
        seen.add(text)
        candidates[DIARY_LABEL_MAP[label]].append({"text": text, "label": f"감성대화 {label}",
                                                   "primary": [DIARY_LABEL_MAP[label].value]})

    # 국립국어원: 감정이 하나만 True인 문장. &others&는 가려진 언급 표시라 지웁니다.
    for path in NIKL_SOURCES:
        for line in path.read_text().splitlines():
            item = json.loads(line)
            labels = [name for name, value in item["output"].items() if value == "True"]
            text = item["input"]["form"].replace("&others&", "").strip()
            if len(labels) != 1 or text in seen:
                continue
            emotion = Emotion(labels[0].upper())
            if emotion not in NIKL_EMOTIONS:
                continue
            seen.add(text)
            candidates[emotion].append({"text": text, "label": f"국립국어원 {labels[0]}", "primary": [emotion.value]})

    random.seed(args.seed)
    items = []
    for emotion, pool in candidates.items():
        picked = random.sample(pool, min(args.per_emotion, len(pool)))
        print(f"{emotion.value}: 후보 {len(pool)}개 중 {len(picked)}개")
        items += picked
    if MANUAL.exists() and not args.exclude:
        manual = json.loads(MANUAL.read_text())
        print(f"직접 작성: {len(manual)}개")
        items += manual
    random.shuffle(items)

    output.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(f"→ {output} ({len(items)}개)")

if __name__ == "__main__":
    main()

# 감성사전.xlsx에서 극성이 뚜렷한 단어만 골라 data/sentiment.json을 만듭니다.
# 감성가: 1(매우 부정) ~ 7(매우 긍정). 4~5는 중립에 가까워 제외합니다.
# 사전을 다시 만들 때만 필요한 스크립트입니다. 실행 전 `pip install openpyxl`이 필요합니다.
import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent
SOURCE = ROOT / "감성사전.xlsx"
OUTPUT = ROOT / "data" / "sentiment.json"

def main():
    rows = openpyxl.load_workbook(SOURCE, read_only=True).active.iter_rows(min_row=2, values_only=True)

    sentiment = {}
    for word, _pos, meaning, score, *_ in rows:
        if word is None or score is None:
            continue
        score = int(score)
        if 4 <= score <= 5:
            continue
        # 같은 단어라도 뜻마다 점수가 다를 수 있어 [점수, 뜻풀이] 목록으로 저장합니다.
        sentiment.setdefault(word.strip(), []).append([score, meaning])

    OUTPUT.write_text(json.dumps(sentiment, ensure_ascii=False, indent=1))
    print(f"단어 {len(sentiment)}개 저장: {OUTPUT}")

if __name__ == "__main__":
    main()

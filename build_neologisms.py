# KoCulture-Dialogues 데이터셋을 받아 신조어별 예시 대화 사전(data/neologisms.json)을 만듭니다.
# 데이터셋: https://huggingface.co/datasets/huggingface-KREW/KoCulture-Dialogues (CC BY-NC-SA 4.0)
# 사전을 다시 만들 때만 필요한 스크립트입니다. 실행 전 `pip install pyarrow`가 필요합니다.
import io
import json
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq

PARQUET_URL = "https://huggingface.co/datasets/huggingface-KREW/KoCulture-Dialogues/resolve/main/data/train-00000-of-00001.parquet"
OUTPUT = Path(__file__).parent / "data" / "neologisms.json"
EXAMPLES_PER_WORD = 2

def main():
    with urllib.request.urlopen(PARQUET_URL) as res:
        rows = pq.read_table(io.BytesIO(res.read())).to_pylist()

    neologisms = {}
    for row in rows:
        examples = neologisms.setdefault(row["title"].strip(), [])
        if len(examples) < EXAMPLES_PER_WORD:
            examples.append([row["question"], row["answer"]])

    OUTPUT.write_text(json.dumps(neologisms, ensure_ascii=False, indent=1))
    print(f"{len(rows)}개 대화에서 신조어 {len(neologisms)}개 저장: {OUTPUT}")

if __name__ == "__main__":
    main()

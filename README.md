# jev

입력한 문장에서 감정을 판독하는 CLI 도구입니다. OpenAI API(`gpt-4.1`, Structured Outputs)로 26가지 감정 중 주 감정과 부 감정, 강도, 신뢰도를 분석하고, 감정별 테루테루보즈 이미지와 함께 결과를 보여줍니다. 부정적인 감정이 강하게 나타나면 대응 방법에 대한 코멘트도 함께 보여줍니다.

## 신조어 처리

입력 문장에 신조어가 있으면 [KoCulture-Dialogues](https://huggingface.co/datasets/huggingface-KREW/KoCulture-Dialogues) 데이터셋에서 그 신조어가 쓰인 예시 대화를 찾아, 참고 자료로 함께 모델에 넘깁니다. 모델이 신조어의 뜻을 문맥으로 파악해 감정을 더 정확히 판독하도록 하기 위한 것입니다. 문장 자체를 표준어로 바꾸지는 않습니다.

- 사전: `data/neologisms.json` (신조어 354개, 단어당 예시 대화 최대 2개)
- 탐지: 입력 문장에 신조어가 그대로 들어 있는지 확인합니다. 한 글자 신조어(`갓`, `각` 등)는 일반 단어와 구분이 안 돼 제외합니다.
- 한계: `사이다`, `고구마`처럼 일반 단어와 같은 신조어는 원래 뜻으로 쓰여도 신조어로 잡힙니다. `~에 진심인 편`처럼 틀 형태인 신조어는 탐지되지 않습니다.

신조어가 탐지되면 모델에는 입력 문장 대신 아래 형식의 텍스트가 user 메시지로 넘어갑니다 (`main.py`의 `build_state`). 신조어가 없으면 입력 문장만 그대로 넘어갑니다.

```
[분석할 문장]
요즘 갓생 사는 게 내 추구미임

[참고: 위 문장에 쓰인 신조어의 용례. 감정 판단 대상이 아니며 신조어의 뜻을 이해하는 데만 사용]
- 추구미: "<예시 대화 1 질문>" / "<예시 대화 1 답변>"
- 추구미: "<예시 대화 2 질문>" / "<예시 대화 2 답변>"
- 갓생: "<예시 대화 1 질문>" / "<예시 대화 1 답변>"
- 갓생: "<예시 대화 2 질문>" / "<예시 대화 2 답변>"
```

예시 대화에도 감정이 담겨 있어 판독에 영향을 줄 수 있으므로, 감정 판단 대상이 아니라는 안내를 함께 넣습니다.

사전을 다시 만들려면:

```bash
pip install pyarrow
python build_neologisms.py
```

## 출력 예시

```
입력: 오랜만에 옛날 사진을 보니까 그때가 그립다

[분석 완료]
<NOSTALGIA 이미지>
주 감정: 향수, 그리움
<SADNESS 이미지>
부 감정: 슬픔
강도:   🟧🟧🟧🟧🟧🟧⬜⬜⬜ (6/9)
신뢰도: 87%
```

주 감정이 부정적인 감정(걱정, 어색함, 지루함, 혼란스러움, 역겨움, 공감적 고통, 부러움·질투, 두려움, 공포, 슬픔)이고 강도가 7 이상이면 아래에 코멘트가 추가됩니다.

```
[대응 코멘트]
<지금 해볼 수 있는 대응 방법 2~3문장>
```

| 항목 | 설명 |
| --- | --- |
| 주 감정 | 가장 두드러진 감정 |
| 부 감정 | 함께 나타나는 감정 |
| 강도 | 1(아주 희미함) ~ 9(통제하기 힘들 정도로 강렬함) |
| 신뢰도 | 주 감정 판독에 대해 모델이 스스로 매긴 확신도 (보정된 확률이 아님) |
| 대응 코멘트 | 부정적인 감정이 강도 7 이상일 때만 표시 |

## 감정 목록 (26가지)

존경(ADMIRATION), 흠모(ADORATION), 심미적 감상(AESTHETIC_APPRECIATION), 즐거움(AMUSEMENT), 걱정(ANXIETY), 경외감(AWE), 어색함(AWKWARDNESS), 지루함(BOREDOM), 차분함(CALMNESS), 혼란스러움(CONFUSION), 간절함(CRAVING), 역겨움(DISGUST), 공감적 고통(EMPATHETIC_PAIN), 황홀경(ENTRANCEMENT), 부러움·질투(ENVY), 흥분됨·신남(EXCITEMENT), 두려움(FEAR), 공포(HORROR), 흥미·호기심(INTEREST), 기쁨(JOY), 향수·그리움(NOSTALGIA), 로맨스(ROMANCE), 슬픔(SADNESS), 만족(SATISFACTION), 공감(SYMPATHY), 승리감(TRIUMPH)

각 감정의 판단 기준은 `main.py`의 `emotion_criteria`에, 코멘트 대상 감정과 강도 기준은 `NEGATIVE_EMOTIONS`, `ADVICE_MIN_INTENSITY`에 정의되어 있습니다.

## 설치

Python 3 가상환경을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 만들고 API 키를 넣습니다.

```
OPENAI_API_KEY=your-api-key
```

## 실행

```bash
python main.py
```

`입력:` 프롬프트에 분석할 문장을 입력하면 결과가 출력됩니다.

> 감정 이미지는 iTerm2 인라인 이미지 프로토콜로 출력되므로 iTerm2(또는 이 프로토콜을 지원하는 터미널)에서만 보입니다. 다른 터미널에서는 이미지 없이 텍스트만 정상 표시됩니다. JOY는 아직 이미지가 없어 생략됩니다.

## 실행 파일 빌드

PyInstaller로 단일 실행 파일을 만들 수 있습니다. `main.spec`에 `emotions/` 폴더가 포함되도록 설정되어 있습니다.

```bash
pip install pyinstaller
pyinstaller main.spec
./dist/main
```

실행 파일도 `OPENAI_API_KEY`가 필요하므로, 실행하는 위치에 `.env`를 두거나 환경 변수로 설정하세요.

## 파일 구성

```
main.py              # 감정 분석 CLI (신조어 탐지, GPT 호출, 결과 출력)
main.spec            # PyInstaller 빌드 설정
emotions/            # 감정별 테루테루보즈 이미지 (<EMOTION>.png)
data/neologisms.json # 신조어별 예시 대화 사전
build_neologisms.py  # 신조어 사전 생성 스크립트
base.ts              # 초기 설계용 TypeScript 스키마 (27가지 감정 버전, 현재 미사용)
```

## 라이선스 참고

`data/neologisms.json`은 Hugging Face KREW의 [KoCulture-Dialogues](https://huggingface.co/datasets/huggingface-KREW/KoCulture-Dialogues)에서 가공한 데이터로, 원 데이터셋의 CC BY-NC-SA 4.0 라이선스를 따릅니다 (비상업적 이용만 가능).

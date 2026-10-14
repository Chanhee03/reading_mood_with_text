# jev

입력한 문장에서 감정을 판독하는 CLI 도구입니다. TypeSafe SDK(`typesafe-sdk`)의 Jev 모델(`system_one`)로 26가지 감정 중 주 감정과 부 감정, 강도, 신뢰도를 분석하고, 감정별 테루테루보즈 이미지와 함께 결과를 보여줍니다.

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

| 항목 | 설명 |
| --- | --- |
| 주 감정 | 가장 두드러진 감정 |
| 부 감정 | 함께 나타나는 감정 |
| 강도 | 1(아주 희미함) ~ 9(통제하기 힘들 정도로 강렬함) |
| 신뢰도 | 주 감정 판독에 대해 Jev가 반환한 confidence |

## 감정 목록 (26가지)

존경(ADMIRATION), 흠모(ADORATION), 심미적 감상(AESTHETIC_APPRECIATION), 즐거움(AMUSEMENT), 걱정(ANXIETY), 경외감(AWE), 어색함(AWKWARDNESS), 지루함(BOREDOM), 차분함(CALMNESS), 혼란스러움(CONFUSION), 간절함(CRAVING), 역겨움(DISGUST), 공감적 고통(EMPATHETIC_PAIN), 황홀경(ENTRANCEMENT), 부러움·질투(ENVY), 흥분됨·신남(EXCITEMENT), 두려움(FEAR), 공포(HORROR), 흥미·호기심(INTEREST), 기쁨(JOY), 향수·그리움(NOSTALGIA), 로맨스(ROMANCE), 슬픔(SADNESS), 만족(SATISFACTION), 공감(SYMPATHY), 승리감(TRIUMPH)

각 감정의 판단 기준은 `main.py`의 `emotion_criteria`에 정의되어 있습니다.

## 설치

Python 3 가상환경을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 만들고 API 키를 넣습니다.

```
TYPESAFE_API_KEY=your-api-key
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

실행 파일도 `TYPESAFE_API_KEY`가 필요하므로, 실행하는 위치에 `.env`를 두거나 환경 변수로 설정하세요.

## 파일 구성

```
main.py      # 감정 분석 CLI (Jev 호출, 결과 출력)
main.spec    # PyInstaller 빌드 설정
emotions/    # 감정별 테루테루보즈 이미지 (<EMOTION>.png)
base.ts      # 초기 설계용 TypeScript 스키마 (27가지 감정 버전, 현재 미사용)
```

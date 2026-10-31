# GPU 효과 증명 실험

목적: "GPU 서버의 LLM이 비개발자의 보안 조치를 실제로 돕는가"를 숫자 한 장으로 보여 줍니다. [roadmap.md](../roadmap.md) 4장에서 해커톤 필수 항목으로 적어 둔 실험입니다(공식 요건 여부는 [README](README.md) 결정 필요 ①에서 확인).

시간 예산: **준비 30분 + 실행 1시간 + 정리 30분**. 21:00 전에 끝내야 발표 자료에 넣을 수 있습니다.

## 1. 비교 조건

| 조건 | 사용자에게 주는 것 | 만드는 방법 |
|---|---|---|
| **A** 스캐너 원문 | 스캐너가 낸 제목·규칙 ID·파일 위치 | 보안엔진 결과 JSON 그대로 |
| **B** GPU 없는 설명 | 아래 2장에서 정함 | 결정 필요 ⑧ |
| **C** GPU LLM | 문맥 분석 + Blue 설명·수정 지시 1회 | `python -m app.llm.check --mode blue` |
| **D** GPU LLM + Red–Blue | C에 Red 검증과 재작성(최대 2회) | `python -m app.llm.check --mode red_blue` |

[docs/llm.md](../llm.md)의 정의대로 **C − B = GPU 효과**, **D − C = Red–Blue 효과**입니다.

## 2. B 조건 정하기 (결정 필요 ⑧)

| 후보 | 장점 | 단점 |
|---|---|---|
| B1. 규칙 템플릿 설명 (LLM 없음): 규칙별로 미리 쓴 고정 문장 | 준비가 빠르고 "LLM이 왜 필요한가"를 바로 보여 줌 | 엄밀히는 "GPU 없는 LLM"이 아님 |
| B2. CPU에서 돌아가는 작은 모델 | 이름 그대로 "GPU 없는 LLM" | 모델 준비·외부 자원 표 추가가 필요하고, 오늘 밤 시간 안에 어려움 |

**추천: B1.** 오늘 밤 안에 끝낼 수 있고, 발표에서 "GPU 없이 할 수 있는 최선(고정 문장)과 비교"라고 정직하게 말할 수 있습니다. B2를 고르면 쓰는 모델을 `docs/external-resources.md`에 추가합니다.

## 3. 데이터

- **데모 저장소**의 실제 검사 결과에서 5~10건. 시크릿·의존성·코드 취약점이 섞이게 고릅니다.
- 시간이 없으면 `backend/tests/fixtures/findings.json`(예시 5건)으로 C·D만 먼저 돌립니다.
- 어떤 건을 골랐는지, 왜 골랐는지 결과 표 아래에 적습니다. 유리한 건만 고르지 않습니다.

```bash
# 데모 저장소 검사 → LLM 입력 꾸러미
python -m security_engine scan --repo-url https://github.com/<소유자>/<데모 저장소> -o outputs/demo-scan.json
python -m security_engine llm-input outputs/demo-scan.json -o outputs/demo-llm-input.json

# C·D 실행 (GPU 서버 8001 터널이 열려 있어야 함). 결과는 outputs/llm-check-<시각>.json
cd backend
python -m app.llm.check --engine-input ../outputs/demo-llm-input.json --mode both
```

## 4. 지표

| 지표 | 재는 법 | 비교 |
|---|---|---|
| **조치 성공률** (핵심) | 조건별 안내문만 같은 AI 코딩툴에 같은 요청 문장으로 넣어 고치게 한 뒤 재검사. "해결됨"이 되고 빌드·테스트가 그대로 통과한 비율 | A·B·C·D |
| 이해도 | 개발 경험 없는 사람 2명 이상에게 조건을 가린 채 보여 주고 "무엇이 문제이고 무엇을 하면 되는지 알겠다"를 5점 척도로 | A·B·C·D |
| Red 통과율 | `check` 출력의 Red 판정, "수동 확인" 비율 | D |
| 한국어 품질 | `check` 출력의 한글 비율, 한자 섞임 | C·D |
| 처리 시간 | `check` 출력의 건당 지연 중앙값 | C·D |

조치 성공률은 사람 판단 없이 재검사 상태로 정해지므로 가장 설득력이 있습니다. 시간이 부족하면 이 지표 하나만이라도 A·C·D로 측정합니다.

## 5. 결과 표 (실험 후 채움)

| 조건 | 건수 | 조치 성공률 | 이해도 (5점) | Red 통과율 | 건당 시간 |
|---|---|---|---|---|---|
| A 스캐너 원문 | | | | — | — |
| B | | | | — | |
| C GPU LLM | | | | — | |
| D GPU LLM + Red–Blue | | | | | |

- 실행 일시, 모델, 데모 저장소 커밋, 사용한 AI 코딩툴, 평가자 수를 표 아래에 적습니다.
- 원본 출력 JSON은 커밋하지 않고(`outputs/`), **GPU 서버 종료(11/2 19:00) 전에 팀 Drive에 백업**합니다.
- 표본이 작으면 작다고 씁니다. 발표에서는 "5건 기준"처럼 건수를 함께 말합니다.

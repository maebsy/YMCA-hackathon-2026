# 팀 협업 규칙

5명이 한 저장소를 빠르고 안전하게 쓰기 위한 규칙입니다.
대부분 **자동으로 검사**되므로 외울 필요는 없습니다. 검사에 걸리면 안내 메시지대로 고치면 됩니다.

## 0. 처음 한 번만

```bash
git clone https://github.com/maebsy/YMCA-hackathon-2026.git
cd YMCA-hackathon-2026
bash scripts/setup-dev.sh      # Windows는 Git Bash에서 실행
cp .env.example .env           # 값은 팀 채팅에서 받아 채우기
```

`setup-dev.sh`는 커밋할 때 **메시지 형식**과 **비밀정보·대용량 파일**을, push할 때 **브랜치 이름**을 검사하는 훅을 켜고, 커밋 메시지 양식을 연결합니다.

## 1. 작업 흐름

```
이슈 → 브랜치 → 커밋 → PR → 승인 1명 + 자동 검사 통과 → Squash 머지
```

1. **이슈**: 할 일은 먼저 이슈로 만듭니다. New issue에서 양식(기능·버그·실험·작업)을 고르면 유형·우선순위·파트 라벨이 자동으로 붙습니다. 맡을 사람은 Assignees에 자기를 넣습니다.
2. **브랜치**: 항상 최신 main에서 만듭니다.
   ```bash
   git switch main && git pull
   git switch -c feat/12-upload-api
   ```
3. **커밋**: 작게, 자주. 형식은 [3장](#3-커밋-메시지)을 보세요.
4. **PR**: `git push -u origin feat/12-upload-api` 후 GitHub에서 PR을 엽니다. 양식을 채우고 본문에 `Closes #12`를 적으면 머지될 때 이슈가 자동으로 닫힙니다. 리뷰어를 1명 지정합니다.
5. **머지**: 승인 1개와 자동 검사 통과가 모두 채워지면 **Squash and merge** 합니다. 머지된 브랜치는 자동으로 지워집니다. 미리 **Enable auto-merge**를 눌러 두면 조건이 채워지는 순간 자동으로 머지됩니다.

## 2. 브랜치 이름

`<타입>/<이슈번호>-<짧은-설명>` — 영문 소문자, 숫자, `-` `_` `.`만 씁니다.

| 예시 | 용도 |
|---|---|
| `feat/12-upload-api` | 기능 |
| `fix/15-ocr-timeout` | 버그 |
| `exp/20-lora-r16` | 실험 |
| `data/8-synthetic-gen` | 데이터 |
| `docs/30-readme` | 문서·발표 |
| `hotfix/demo-crash` | 제출 직전 긴급 수정 |

타입은 커밋 타입과 같고, `hotfix`가 하나 더 있습니다. `main`에는 아무도 직접 push할 수 없습니다.

이름이 틀리면 **push할 때 훅이 막고**, 훅 없이 올라가더라도 **PR의 `branch-name` 검사가 머지를 막습니다.**

## 3. 커밋 메시지

```
<타입>(<범위>): <요약>
```

- 첫 줄만 필수입니다. 72자 이내, 요약은 한국어로 써도 됩니다. 범위는 생략할 수 있습니다.
- `git commit`을 `-m` 없이 실행하면 양식이 열립니다.

| 타입 | 언제 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작은 같고 구조만 개선 |
| `perf` | 성능 개선 |
| `test` | 테스트 |
| `docs` | 문서, README, 발표 자료 |
| `style` | 포맷, 공백 |
| `chore` | 설정, 잡무 |
| `ci` | GitHub Actions |
| `build` | 의존성, 빌드 |
| `revert` | 되돌리기 |
| `data` | 데이터 수집·전처리·합성 |
| `model` | 학습, 파인튜닝, 모델 교체 |
| `exp` | 실험 (결과는 실험 이슈에 기록) |

범위 예: `api` `web` `model` `data` `infra` `docs`

```
feat(api): 이미지 위험도 판별 엔드포인트 추가
fix(web): 업로드 실패 시 무한 로딩 수정
data: 합성 학습 데이터 생성 스크립트 추가
exp(model): LoRA r=16과 r=32 정확도 비교
```

## 4. PR 규칙

- **제목도 커밋 규칙을 따릅니다.** Squash 머지되면 PR 제목이 main의 커밋 제목이 됩니다.
- **본문에 `Closes #이슈번호`를 적습니다.** 이슈 없이 하는 오타 수정 같은 PR은 `no-issue` 라벨을 붙입니다.
- **작게 만듭니다.** 300줄 이하를 권장합니다. 크면 리뷰가 늦어지고 충돌이 납니다.
- **외부 자원 표를 같이 고칩니다.** 라이브러리·모델·데이터셋·API를 새로 쓰면 같은 PR에서 [`docs/external-resources.md`](docs/external-resources.md)에 추가합니다. 빠지면 **실격**입니다.

### 자동 검사 (모두 통과해야 머지 가능)

| 검사 | 내용 |
|---|---|
| `pr-title` | PR 제목 형식 |
| `branch-name` | 브랜치 이름 형식 |
| `commit-messages` | PR 안 모든 커밋의 메시지 형식 |
| `issue-link` | 본문의 `Closes #번호` (또는 `no-issue` 라벨) |
| `lint` | 파이썬 문법 오류, 정의되지 않은 이름 |
| `secret-scan` | API 키·토큰 유출 (gitleaks) |

`backend/`나 `compose.yaml`이 바뀐 PR에서는 `compose` 검사(이미지 빌드, DB 연결까지 헬스체크)도 돕니다. 필수 검사는 아니지만 실패하면 다른 사람의 `docker compose up`이 깨지니 고치고 머지하세요.

## 5. 리뷰

- 리뷰 요청을 받으면 **30분 안에** 봅니다. 해커톤에서는 리뷰 대기가 곧 병목입니다.
- 꼼꼼함보다 **main을 깨뜨리지 않는지**를 봅니다: 실행되는지, 비밀정보가 없는지, 다른 사람 코드를 망가뜨리지 않는지.
- 사소한 의견은 `nit:`을 붙이고 승인합니다. 리뷰 대화가 모두 resolve되어야 머지됩니다.

## 6. 하지 말 것

- `.env`, API 키, 토큰, 서버 비밀번호·OTP 커밋. 훅과 CI가 막지만, **push된 순간 유출**입니다. 실수로 올렸으면 바로 팀장에게 알리고 키를 폐기한 뒤 재발급합니다.
- 개인정보, 실데이터, 5MB가 넘는 데이터·모델 파일 커밋. 서버에 두고 경로만 기록합니다.
- `--no-verify`로 훅을 건너뛰는 것.

## 7. 라벨과 마일스톤

| 구분 | 라벨 | 붙는 방법 |
|---|---|---|
| 유형 | `type: feature` `type: bug` `type: experiment` `type: task` | 양식에 따라 자동 |
| 우선순위 | `P0` 데모 필수 → `P1` 중요 → `P2` 있으면 좋음 | 양식에서 고르면 자동 |
| 파트 | `area: AI·모델` `area: 데이터` `area: 백엔드` `area: 프론트·데모` `area: 인프라` `area: 문서·발표` | 양식에서 고르면 자동 |
| 상태 | `blocked` 막힘, `no-issue` 이슈 없는 PR | 직접 |

마일스톤은 `D1` (10/30), `D2` (10/31), `D3 제출` (11/1 13:00), `2차 발표` (11/2)입니다. 이슈에 직접 지정합니다.

**P0 이슈부터** 처리합니다. 막히면 `blocked` 라벨을 붙이고 팀 채팅에 바로 알립니다.

## 8. 자주 막히는 상황

### 커밋 메시지를 잘못 썼다

마지막 커밋 하나라면:
```bash
git commit --amend -m "fix: 올바른 메시지"
git push --force-with-lease      # 이미 push했을 때만
```

여러 개라면 브랜치의 커밋을 하나로 합치는 게 가장 쉽습니다:
```bash
git fetch origin
git reset --soft $(git merge-base HEAD origin/main)
git commit -m "feat(api): 올바른 메시지"
git push --force-with-lease
```

### 브랜치 이름을 잘못 지었다

push 전이라면 로컬에서 이름만 바꾸면 됩니다:
```bash
git branch -m 옛-이름 feat/12-new-name
```

이미 push했다면 GitHub 저장소의 **Branches** 화면에서 브랜치 옆 연필 아이콘으로 이름을 바꿉니다. 열린 PR은 자동으로 따라가고, 로컬에서 해야 할 명령은 GitHub가 안내해 줍니다.

### main이 바뀌어서 충돌이 난다

```bash
git fetch origin
git merge origin/main     # 충돌 난 파일을 고친 뒤
git add <고친 파일>
git commit                # 머지 커밋은 형식 검사에서 빠집니다
git push
```

충돌이 없으면 PR 화면의 **Update branch** 버튼으로도 됩니다.

### 커밋 훅이 비밀정보라고 막는데 아닌 것 같다

`--no-verify`로 넘기지 말고 팀장에게 먼저 보여 주세요.

### 제출 직전 긴급 수정

`hotfix/` 브랜치로 PR을 엽니다. 팀장은 관리자 권한으로 승인 없이 머지할 수 있습니다. main에 직접 push하는 것은 팀장도 막혀 있습니다.

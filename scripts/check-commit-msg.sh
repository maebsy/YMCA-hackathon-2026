#!/usr/bin/env bash
# 커밋 메시지·PR 제목이 팀 규칙(Conventional Commits)을 따르는지 검사합니다.
# 커밋 훅(.githooks/commit-msg)과 CI(.github/workflows/pr-rules.yml)가 같이 씁니다.
#
#   bash scripts/check-commit-msg.sh "feat(api): 제목"
#   bash scripts/check-commit-msg.sh --file .git/COMMIT_EDITMSG
set -euo pipefail
export LC_ALL=C.UTF-8   # 한글 글자 수를 바이트가 아닌 글자 단위로 셈

TYPES="feat|fix|refactor|perf|test|docs|style|chore|ci|build|revert|data|model|exp"
MAX_LEN=72

if [[ "${1:-}" == "--file" ]]; then
  # '#' 주석과 빈 줄을 건너뛴 첫 줄이 제목
  header=$(grep -v '^#' "$2" | grep -v '^[[:space:]]*$' | head -n 1 || true)
else
  header="${1:-}"
fi

# git이 자동으로 만드는 메시지는 통과
case "$header" in
  "Merge "* | "Revert \""* | "fixup! "* | "squash! "* | "amend! "*) exit 0 ;;
esac

pattern="^($TYPES)(\([a-z0-9._/-]+\))?!?: [^ ].*"
if [[ ! "$header" =~ $pattern ]]; then
  cat >&2 <<EOF
❌ 커밋 메시지 형식이 맞지 않습니다: "$header"

   형식  <타입>(<범위>): <요약>      범위는 생략 가능
   예시  feat(api): 이미지 위험도 판별 엔드포인트 추가
         fix: 업로드 실패 시 무한 로딩 수정
   타입  ${TYPES//|/, }

   자세한 규칙과 고치는 법: CONTRIBUTING.md
EOF
  exit 1
fi

if (( ${#header} > MAX_LEN )); then
  echo "❌ 첫 줄이 너무 깁니다 (${#header}자, 최대 ${MAX_LEN}자): \"$header\"" >&2
  exit 1
fi

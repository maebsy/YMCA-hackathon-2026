#!/usr/bin/env bash
# 브랜치 이름이 팀 규칙을 따르는지 검사합니다.
# push 훅(.githooks/pre-push)과 CI(.github/workflows/pr-rules.yml)가 같이 씁니다.
#
#   bash scripts/check-branch-name.sh feat/12-upload-api
set -euo pipefail

branch="${1:?브랜치 이름을 넘겨 주세요}"
pattern='^(feat|fix|refactor|perf|test|docs|style|chore|ci|build|revert|data|model|exp|hotfix)/[a-z0-9][a-z0-9._-]*$'

if [[ "$branch" =~ $pattern ]]; then
  exit 0
fi

cat >&2 <<EOF
❌ 브랜치 이름이 규칙에 맞지 않습니다: $branch

   형식  <타입>/<이슈번호>-<짧은-설명>      예) feat/12-upload-api
   영문 소문자, 숫자, - _ . 만 쓸 수 있습니다.

   이름 바꾸기   git branch -m $branch feat/12-new-name
   자세한 규칙   CONTRIBUTING.md
EOF
exit 1

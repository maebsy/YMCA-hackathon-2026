#!/usr/bin/env bash
# 내 브랜치가 고친 파일을 아직 머지 안 된 다른 브랜치도 고치고 있는지, 실제로 충돌하는지 미리 봅니다.
# 작업을 시작할 때와 PR을 올리기 전에 실행합니다 (AGENTS.md 1장).
#
#   bash scripts/check-overlap.sh             # 지금 브랜치 기준 (커밋 안 한 변경 포함)
#   bash scripts/check-overlap.sh feat/12-x   # 다른 브랜치 기준
set -euo pipefail

target="${1:-HEAD}"
stale_hours=12
git fetch -q origin

base=$(git merge-base origin/main "$target")
mine=$(git diff --name-only "$base" "$target")
if [[ "$target" == "HEAD" ]]; then
  mine=$(printf '%s\n%s\n%s\n' "$mine" "$(git diff --name-only)" "$(git diff --name-only --cached)")
fi
mine=$(printf '%s\n' "$mine" | sed '/^$/d' | sort -u)

if [[ -z "$mine" ]]; then
  echo "main과 다른 파일이 없습니다."
  exit 0
fi

me=$(git rev-parse --abbrev-ref "$target")
me="${me#origin/}"
main_tree=$(git rev-parse 'origin/main^{tree}')
# Squash 머지된 브랜치를 알아보기 위해 main 최근 커밋들의 변경 지문을 모아 둡니다
main_patches=$(git log -p -n 300 origin/main | git patch-id --stable | cut -d' ' -f1)
now=$(date +%s)
found=0

for ref in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin); do
  case "$ref" in origin/HEAD|origin/main|origin|"origin/$me") continue ;; esac
  # main보다 앞선 커밋이 없으면 이미 머지된 브랜치
  [[ "$(git rev-list --count "origin/main..$ref")" -eq 0 ]] && continue
  ref_base=$(git merge-base origin/main "$ref")
  # Squash 머지된 브랜치: 합쳐도 main이 그대로이거나, 전체 변경이 main의 커밋 하나와 같음
  merged=$(git merge-tree --write-tree origin/main "$ref" 2>/dev/null | head -1) || merged=""
  [[ "$merged" == "$main_tree" ]] && continue
  patch=$(git diff "$ref_base" "$ref" | git patch-id --stable | cut -d' ' -f1)
  [[ -n "$patch" ]] && grep -qx "$patch" <<<"$main_patches" && continue

  theirs=$(git diff --name-only "$ref_base" "$ref" | sort -u)
  common=$(comm -12 <(printf '%s\n' "$mine") <(printf '%s\n' "$theirs"))
  [[ -z "$common" ]] && continue

  found=1
  if git merge-tree --write-tree "$target" "$ref" >/dev/null 2>&1; then
    status="같은 파일, 자동 병합됨"
  else
    status="충돌"
  fi
  age=$(( (now - $(git log -1 --format=%ct "$ref")) / 3600 ))
  note=""
  (( age >= stale_hours )) && note=" · ${age}시간 멈춤, 이미 머지·폐기된 브랜치일 수 있음"
  echo "■ $ref — $status (마지막 커밋: $(git log -1 --format='%an, %cr' "$ref")$note)"
  printf '%s\n' "$common" | sed 's/^/    /'
done

if [[ $found -eq 0 ]]; then
  echo "머지 안 된 다른 브랜치와 겹치는 파일이 없습니다."
else
  echo
  echo "충돌이 있으면 그 브랜치 작성자와 먼저 이야기하고, 누가 먼저 머지할지 정하세요."
fi

#!/usr/bin/env bash
# 클론한 뒤 한 번만 실행하세요:  bash scripts/setup-dev.sh
# 커밋 메시지·비밀정보 검사 훅과 커밋 메시지 양식을 켭니다.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

git config core.hooksPath .githooks
git config commit.template .gitmessage
chmod +x .githooks/* scripts/*.sh 2>/dev/null || true

echo "✅ 설정 완료"
echo "   - 커밋할 때 메시지 형식, 비밀정보, 대용량 파일을 자동으로 검사합니다"
echo "   - git commit 을 -m 없이 실행하면 메시지 양식이 열립니다"

if [[ -z "$(git config user.email || true)" ]]; then
  echo ""
  echo "⚠️  git 사용자 정보가 없습니다. 아래 두 줄을 실행하세요."
  echo "   이메일은 GitHub Settings > Emails 에 있는 noreply 주소를 쓰면 개인 메일이 공개되지 않습니다."
  echo "   git config --global user.name  \"GitHub아이디\""
  echo "   git config --global user.email \"숫자+아이디@users.noreply.github.com\""
fi

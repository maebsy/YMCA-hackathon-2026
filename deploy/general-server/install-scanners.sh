#!/usr/bin/env bash
# 보안엔진 스캐너 3종을 사용자 홈에 설치합니다 (Linux x86_64). 공식 GitHub 릴리스에서 받고 SHA-256을 확인합니다.
#   bash deploy/general-server/install-scanners.sh
# 설치 위치: ~/.local/share/72hours/scanners/bin  (sudo 불필요, 시스템 패키지를 바꾸지 않음)
# 설치 후 ~/.config/72hours/backend.env 에 출력된 SECURITY_ENGINE_*_BIN 세 줄을 넣고 72hours-backend를 재시작하세요.
set -euo pipefail
umask 022

[[ "$(uname -s)-$(uname -m)" == "Linux-x86_64" ]] || { echo "Linux x86_64 전용입니다" >&2; exit 1; }
command -v git >/dev/null || { echo "git이 필요합니다 (저장소 clone용)" >&2; exit 1; }

dest="$HOME/.local/share/72hours/scanners/bin"
mkdir -p "$dest"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fetch() {  # url sha256 out
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c --quiet - || { echo "체크섬 불일치: $1" >&2; exit 1; }
}

# Opengrep 1.33.1 (LGPL-2.1). 해시는 릴리스 파일을 받아 직접 계산해 고정한 값입니다
fetch "https://github.com/opengrep/opengrep/releases/download/v1.33.1/opengrep_manylinux_x86" \
  46e8133cc490f9f50518061590ce2f6be5a08afaeda034471c0ceda4b3899808 "$tmp/opengrep"
install -m 755 "$tmp/opengrep" "$dest/opengrep"

# Gitleaks 8.30.1 (MIT). 해시는 공식 gitleaks_8.30.1_checksums.txt 값
fetch "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz" \
  551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb "$tmp/gitleaks.tgz"
tar -xzf "$tmp/gitleaks.tgz" -C "$tmp" gitleaks
install -m 755 "$tmp/gitleaks" "$dest/gitleaks"

# OSV-Scanner 2.7.0 (Apache-2.0). 해시는 공식 osv-scanner_SHA256SUMS 값
fetch "https://github.com/google/osv-scanner/releases/download/v2.7.0/osv-scanner_linux_amd64" \
  160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b "$tmp/osv-scanner"
install -m 755 "$tmp/osv-scanner" "$dest/osv-scanner"

echo "설치 완료: $dest"
"$dest/opengrep" --version
"$dest/gitleaks" version
"$dest/osv-scanner" --version | head -1
cat <<EOF

# ~/.config/72hours/backend.env 에 추가:
SECURITY_ENGINE_SEMGREP_BIN=$dest/opengrep
SECURITY_ENGINE_GITLEAKS_BIN=$dest/gitleaks
SECURITY_ENGINE_OSV_BIN=$dest/osv-scanner
EOF

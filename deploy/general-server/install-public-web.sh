#!/usr/bin/env bash
# Explicit opt-in: install the HTTPS system unit without starting it.
set -euo pipefail
umask 077
runtime_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test -s "$HOME/.config/72hours/public-web.env"
test -x "$HOME/.local/share/72hours/bin/caddy"
mkdir -p "$HOME/apps/72hours/runtime"
cp "$runtime_dir/Caddyfile.public" "$HOME/apps/72hours/runtime/Caddyfile.public"
unit_file="$(mktemp)"
trap 'rm -f -- "$unit_file"' EXIT
python3 - "$runtime_dir/systemd/72hours-public-web.service.in" "$unit_file" <<'PY'
import getpass
from pathlib import Path
import sys
home = str(Path.home())
user = getpass.getuser()
if any(character in home + user for character in '\n\r%"\\ '):
    raise SystemExit("Unsupported account name or home path")
text = Path(sys.argv[1]).read_text().replace("@USER@", user).replace("@HOME@", home)
Path(sys.argv[2]).write_text(text)
PY
sudo install -m 0644 "$unit_file" /etc/systemd/system/72hours-public-web.service
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/72hours-public-web.service
echo "Prepared public HTTPS unit. Validate DNS, ingress, and private env before enabling it."

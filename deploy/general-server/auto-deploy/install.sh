#!/usr/bin/env bash
# Install a pinned controller, never change application symlinks or restart the app here.
set -euo pipefail
umask 077
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
control="$HOME/apps/72hours/auto-deploy"
mkdir -p "$control/runtime" "$HOME/.config/systemd/user/72hours-backend.service.d"
exec 9>"$control/deploy.lock"
flock -n 9
for file in deploy.py deployment_entry.py snapshot.py; do
  if [[ "$source_dir" != "$control/runtime" ]]; then cp "$source_dir/$file" "$control/runtime/$file"; fi
done
# 직접 설치한 사본은 main이 같은 내용이 될 때까지 자기 갱신으로 되돌리지 않습니다 (#151)
if [[ "$source_dir" != "$control/runtime" ]]; then touch "$control/runtime-pinned"; fi
if [[ ! -f "$control/control-token" ]]; then
  python3 -c 'import secrets; print(secrets.token_hex(32))' > "$control/control-token"
fi
chmod 600 "$control/control-token"
cat > "$HOME/.config/systemd/user/72hours-backend.service.d/deployment-guard.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=%h/apps/72hours/current/.venv/bin/python -m uvicorn deployment_entry:create_app --factory --app-dir %h/apps/72hours/auto-deploy/runtime --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
EOF
cat > "$HOME/.config/systemd/user/72hours-auto-deploy.service" <<'EOF'
[Unit]
Description=72hours main pull deployment (CI gate, staged build, rollback)
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/apps/72hours/auto-deploy/runtime/deploy.py
EnvironmentFile=-%h/.config/72hours/auto-deploy.env
Environment=PYTHONDONTWRITEBYTECODE=1
TimeoutStartSec=25min
UMask=0077
Nice=10
NoNewPrivileges=true
EOF
cat > "$HOME/.config/systemd/user/72hours-auto-deploy.timer" <<'EOF'
[Unit]
Description=Check reviewed main for deployment every two minutes

[Timer]
OnActiveSec=2min
OnUnitInactiveSec=2min
AccuracySec=10s
Unit=72hours-auto-deploy.service

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
echo 'Prepared only. Validate --prepare-only, perform initial --bootstrap cutover, then enable --now 72hours-auto-deploy.timer.'

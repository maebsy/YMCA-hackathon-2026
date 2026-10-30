#!/usr/bin/env bash
# Prepare a new immutable backend release and user services; never start/restart implicitly.
set -euo pipefail
umask 077
source_dir="$(realpath "${1:?usage: bash install.sh ~/apps/72hours/releases/COMMIT}")"
runtime_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_root="$HOME/apps/72hours"
config_dir="$HOME/.config/72hours"
case "$source_dir" in "$app_root/releases/"*) ;; *) echo "Source must be a dedicated release under $app_root/releases" >&2; exit 1 ;; esac
test -f "$source_dir/backend/requirements.txt"
test -f "$source_dir/backend/app/main.py"
if [[ -e "$app_root/current" && ! -L "$app_root/current" ]]; then
  echo "Refusing to replace an unmanaged current directory" >&2
  exit 1
fi
if [[ -e "$source_dir/.venv" ]]; then
  echo "Release environment already exists; use a new release directory" >&2
  exit 1
fi
"$HOME/.local/bin/uv" venv --python /usr/bin/python3 "$source_dir/.venv"
"$HOME/.local/bin/uv" pip install --python "$source_dir/.venv/bin/python" -r "$source_dir/backend/requirements.txt"
mkdir -p "$config_dir" "$HOME/.config/systemd/user" "$HOME/.local/share/72hours" "$app_root/runtime"
chmod 700 "$config_dir" "$HOME/.local/share/72hours"
cp "$runtime_dir/Caddyfile" "$app_root/runtime/Caddyfile"
cp "$runtime_dir"/systemd/72hours-*.service "$HOME/.config/systemd/user/"
if [[ ! -e "$config_dir/web.env" ]]; then
  printf '%s\n' 'SITE_ADDRESS=http://127.0.0.1:8080' 'WEB_BIND=127.0.0.1' > "$config_dir/web.env"
fi
if [[ ! -e "$config_dir/gpu-ssh.conf" ]]; then
  cp "$runtime_dir/gpu-ssh.conf.example" "$config_dir/gpu-ssh.conf"
fi
"$HOME/.local/share/72hours/bin/caddy" validate --config "$app_root/runtime/Caddyfile" --adapter caddyfile
ln -s "$source_dir" "$app_root/current.new"
mv -Tf "$app_root/current.new" "$app_root/current"
systemctl --user daemon-reload
echo "Prepared. Configure private credentials/SSH trust, then explicitly start the services. Frontend remains disabled."

"""일반 서버에서 실행. 읽기 전용 검증 서버만 새 user unit으로 등록합니다."""
from pathlib import Path
import subprocess


def main():
    root = Path.home()/'apps/72hours/validation'
    script = root/'code/serve.py'
    if not script.is_file() or not (root/'current/index.html').is_file():
        raise RuntimeError('serve.py와 public 산출물을 먼저 업로드하세요.')
    unit = Path.home()/'.config/systemd/user/72hours-validation.service'
    content = f'''[Unit]
Description=72hours read-only validation evidence
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {script} --public {root}/current --port 8767
Restart=on-failure
UMask=0077
NoNewPrivileges=true
MemoryMax=128M

[Install]
WantedBy=default.target
'''
    if unit.exists() and unit.read_text() != content:
        raise RuntimeError('기존 검증 unit 내용이 다릅니다. 자동 덮어쓰기를 중단합니다.')
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(content)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', '72hours-validation'], check=True)


if __name__ == '__main__':
    main()

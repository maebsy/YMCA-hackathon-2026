"""완료된 검증의 public 파일만 별도 디렉터리에 업로드하고 원자적으로 전환합니다."""
import argparse
from pathlib import Path
import re
import subprocess
import time


def publish(alias, output):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', alias):
        raise ValueError('SSH config 별칭만 허용합니다.')
    public = output.resolve()/'public'
    files = sorted(p for p in public.iterdir() if p.is_file() and not p.is_symlink()
                   and re.fullmatch(r'[a-z0-9-]+\.(html|json|png)', p.name))
    if not {'index.html', 'results.json'} <= {p.name for p in files}:
        raise ValueError('완성된 public 산출물이 없습니다.')
    remote = 'apps/72hours/validation/releases/' + str(time.time_ns())
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', alias]
    subprocess.run(ssh + ['umask 077 && mkdir -p ' + remote], check=True, timeout=20)
    for path in files:
        subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(path), alias+':'+remote+'/'+path.name],
                       check=True, timeout=60)
    # Paths contain only constant segments and a numeric run ID. Keep prior releases for rollback.
    subprocess.run(ssh + ['ln -sfn releases/' + remote.rsplit('/', 1)[1]
        + ' apps/72hours/validation/current.next && mv -Tf apps/72hours/validation/current.next apps/72hours/validation/current'],
        check=True, timeout=20)
    print('공개 산출물 전환 완료: /validation/ (private 파일은 전송하지 않음)')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ssh', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    publish(args.ssh, args.output)

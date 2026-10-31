"""선택적 운영 증거: 기존 unit 상태와 GPU 사용률만 읽습니다. 자격 파일·로그는 읽지 않습니다."""
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import threading

from evidence import atomic_json, now

UNITS = ('72hours-backend', '72hours-frontend', '72hours-mcp', '72hours-quick-web', '72hours-quick-tunnel')


def ssh(alias, command):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,100}', alias):
        raise ValueError('SSH config 별칭 형식이 올바르지 않습니다.')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', alias, command],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('SSH 접속 또는 운영 조회 실패')
    return result.stdout


def ensure_running(server):
    # `start` is a no-op for active units. Never restart a live tunnel or change its configuration.
    ssh(server, 'systemctl --user start ' + ' '.join(UNITS))


class Monitor:
    def __init__(self, public, server=None, gpu=None):
        self.public, self.server, self.gpu = public, server, gpu
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.samples = []

    def run(self):
        while not self.stopped.is_set():
            sample = {'at': now()}
            for kind, alias in (('server', self.server), ('gpu', self.gpu)):
                if not alias:
                    sample[kind] = {'status': 'not_requested'}
                    continue
                try:
                    if kind == 'server':
                        output = ssh(alias, 'systemctl --user show ' + ' '.join(UNITS) + ' --property=Id --property=ActiveState')
                        units = {}
                        for block in output.strip().split('\n\n'):
                            fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
                            units[fields.get('Id', 'unknown')] = fields.get('ActiveState', 'unknown')
                        sample[kind] = {'units': units}
                    else:
                        output = ssh(alias, 'nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits')
                        sample[kind] = {'devices': [{'name': row[0].strip(), 'utilization_percent': float(row[1]),
                            'memory_used_mib': float(row[2]), 'memory_total_mib': float(row[3])}
                            for row in csv.reader(io.StringIO(output))]}
                except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
                    sample[kind] = {'status': 'unavailable', 'notice': 'VPN·SSH·조회 명령 상태를 확인하세요. API 증거와 구분합니다.'}
            self.samples.append(sample)
            self.samples = self.samples[-180:]
            atomic_json(self.public/'operations.json', {'samples': self.samples,
                'notice': '동시간대 운영 스냅샷이며 특정 작업만의 GPU 사용량을 분리한 수치는 아닙니다.'})
            self.stopped.wait(20)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread.is_alive():
            self.thread.join(timeout=32)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--server', required=True)
    p.add_argument('--ensure-running', action='store_true')
    args = p.parse_args()
    if args.ensure_running:
        ensure_running(args.server)
    print(json.dumps({'status': ssh(args.server, 'systemctl --user is-active ' + ' '.join(UNITS)).splitlines()}))

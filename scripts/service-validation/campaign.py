"""한 번의 관리형 재검증: 중복 실행 방지, 표본 순환, 실행별 저장, 결과 게시. 예약은 Codex가 담당합니다."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from discover import discover
from evidence import atomic_json
from publish import publish


@contextmanager
def lock(path):
    with path.open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('다른 검증 실행이 진행 중입니다. 중복 접수하지 않습니다.') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--server-ssh')
    p.add_argument('--gpu-ssh')
    p.add_argument('--discover', action='store_true')
    p.add_argument('--publish', action='store_true')
    p.add_argument('--skip-browser', action='store_true')
    args = p.parse_args()
    args.archive.mkdir(parents=True, exist_ok=True)
    if args.publish and not args.server_ssh:
        p.error('--publish에는 --server-ssh가 필요합니다.')
    with lock(args.archive/'campaign.lock'):
        state_path = args.archive/'campaign.json'
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'next': 0}
        index = state['next']
        # Reserve index before dispatch, so interruption cannot silently reuse a previous run.
        atomic_json(state_path, {'next': index+1})
        output = args.archive/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(time.time_ns()))
        output.mkdir()
        repos = json.loads(Path(__file__).with_name('repositories.json').read_text(encoding='utf-8'))
        discovery = {'status': 'not_requested'}
        if args.discover:
            try:
                candidates = discover('topic:github-pages language:HTML stars:>50', 5)
                repos.append(candidates[index % len(candidates)])
                discovery = {'status': 'done', 'candidate': repos[-1]}
            except RuntimeError as exc:
                discovery = {'status': 'failed', 'detail': str(exc)}
        manifest = output/'repositories.json'
        atomic_json(manifest, repos)
        cmd = [sys.executable, str(Path(__file__).with_name('runner.py')), '--base-url', args.base_url,
               '--output', str(output), '--repos-file', str(manifest), '--max-repos', '4', '--llm-per-repo', '2',
               '--sample-offset', str(index*2), '--max-run-seconds', '900', '--rescan', '--mcp', '--incident-drafts']
        if not args.skip_browser:
            cmd.append('--browser')
        for option, value in (('--server-ssh', args.server_ssh), ('--gpu-ssh', args.gpu_ssh)):
            if value:
                cmd.extend([option, value])
        # The worker has its own deadline and writes resumable receipts. Avoid force-killing live work.
        result = subprocess.run(cmd, check=False)
        if (output/'public/results.json').exists():
            from evidence import Evidence
            data = json.loads((output/'private/state.json').read_text(encoding='utf-8'))
            evidence = Evidence(output, data['settings'], True)
            evidence.data['campaign'] = {'sequence': index, 'discovery': discovery}
            if args.server_ssh:
                from quality_probe import collect
                try:
                    evidence.data['engine_quality'] = collect(args.server_ssh, evidence.public)
                    evidence.check(evidence.data, '엔진 설계 적합성 정답 검증',
                                   'pass' if evidence.data['engine_quality']['status']=='passed' else 'fail',
                                   evidence.data['engine_quality'])
                except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
                    evidence.check(evidence.data, '엔진 설계 적합성 정답 검증', 'fail',
                                   '실행·수집 실패. 이전 결과를 이번 결과로 재사용하지 않습니다.')
                if evidence.data.get('engine_quality',{}).get('status') != 'passed':
                    evidence.data['status'] = 'failed'
                    result.returncode = 1
            evidence.save()
            if args.publish:
                publish(args.server_ssh, output)
        print(json.dumps({'exit_code': result.returncode, 'output': str(output), 'sequence': index}))
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())

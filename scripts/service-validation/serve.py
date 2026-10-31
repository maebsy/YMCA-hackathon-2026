"""검증 산출물만 제공하는 읽기 전용 서버. private/와 디렉터리 목록은 노출하지 않습니다."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote


def history(archives):
    runs = []
    seen = set()
    if not archives.is_dir():
        return {'runs': runs}
    for directory in sorted(archives.iterdir(), reverse=True):
        if len(runs) >= 100:
            break
        if not re.fullmatch(r'\d{16,22}', directory.name) or directory.is_symlink() or not directory.is_dir():
            continue
        path = directory/'results.json'
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 8*1024*1024:
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            identity = data.get('run_id') or data.get('started_at')
            if identity in seen:
                continue
            # A partially uploaded release has no index until all publication files arrive.
            if not (directory/'index.html').is_file():
                continue
            seen.add(identity)
            checks = data.get('checks', []) + [x for c in data.get('cases', []) for x in c.get('checks', [])] + data.get('browser', {}).get('checks', [])
            runs.append({'id': directory.name, 'started_at': data.get('started_at'), 'finished_at': data.get('finished_at'),
                'status': data.get('status'), 'cases': len(data.get('cases', [])),
                'counts': {k: sum(c['status'] == k for c in checks) for k in ('pass', 'fail', 'warn', 'skipped')},
                'failures': data.get('failures', []), 'path': '/validation/runs/'+directory.name+'/index.html'})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {'runs': runs, 'notice': '최근 100개 게시 실행. 같은 증상의 반복 관측이며, 재등장하지 않았다는 이유만으로 해결 처리하지 않습니다.'}


def handler(public):
    public = public.absolute()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/validation':
                self.send_response(307)
                self.send_header('Location', '/validation/')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if path == '/validation/history.json':
                body = json.dumps(history(public.parent/'releases'), ensure_ascii=False).encode()
                return self.respond(body, '.json')
            if path == '/validation/history.html':
                return self.respond(Path(__file__).with_name('history.html').read_bytes(), '.html')
            archive = re.fullmatch(r'/validation/runs/(\d{16,22})/([a-z0-9-]+\.(?:html|json|png|md))', path)
            if archive:
                root = public.parent/'releases'/archive[1]
                if root.is_symlink() or not root.is_dir():
                    self.send_error(404)
                    return
                root, name = root.resolve(), archive[2]
            else:
                root = public.resolve()
                name = path.removeprefix('/validation/').lstrip('/') or 'index.html'
            if not re.fullmatch(r'[a-z0-9-]+\.(html|json|png|md)', name):
                self.send_error(404)
                return
            target = (root/name).resolve()
            if target.parent != root or not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.respond(body, target.suffix)

        def respond(self, body, suffix):
            self.send_response(200)
            self.send_header('Content-Type', {'.html': 'text/html; charset=utf-8', '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.md': 'text/plain; charset=utf-8'}[suffix])
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    if not args.public.is_dir() or not args.public.is_absolute() or not 1024 <= args.port <= 65535:
        parser.error('존재하는 절대 public 디렉터리 및 포트1024~65535가 필요합니다.')
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.public)).serve_forever()

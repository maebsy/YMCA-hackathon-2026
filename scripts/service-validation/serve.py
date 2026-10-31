"""검증 산출물만 제공하는 읽기 전용 서버. private/와 디렉터리 목록은 노출하지 않습니다."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote


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
            if path in ('/validation', '/validation/'):
                name = 'index.html'
            elif path.startswith('/validation/'):
                name = path.removeprefix('/validation/')
            elif path == '/':
                name = 'index.html'
            else:
                name = path.lstrip('/')
            if not re.fullmatch(r'[a-z0-9-]+\.(html|json|png)', name):
                self.send_error(404)
                return
            root = public.resolve()
            target = (root/name).resolve()
            if target.parent != root or not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'.html': 'text/html; charset=utf-8', '.json': 'application/json; charset=utf-8', '.png': 'image/png'}[target.suffix])
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

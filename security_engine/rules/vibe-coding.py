# Semgrep 규칙 테스트용 파일 (실행되는 코드가 아님)
import os
import subprocess

import requests
from flask import Flask

app = Flask(__name__)


def handler(cur, uid, name):
    # ruleid: python-sql-format
    cur.execute(f"SELECT * FROM t WHERE id={uid}")
    # ruleid: python-sql-format
    cur.execute("SELECT * FROM t WHERE name='%s'" % name)
    # ok: python-sql-format
    cur.execute("SELECT * FROM t WHERE id=%s", (uid,))

    # ruleid: python-shell-true
    subprocess.run("ls " + name, shell=True)
    # ruleid: python-shell-true
    os.system("ls " + name)
    # ok: python-shell-true
    subprocess.run(["ls", name])

    # ruleid: tls-verify-disabled-python
    requests.get("https://example.com", verify=False)
    # ok: tls-verify-disabled-python
    requests.get("https://example.com")


# ruleid: python-flask-debug
app.run(host="0.0.0.0", debug=True)
# ok: python-flask-debug
app.run(host="0.0.0.0")

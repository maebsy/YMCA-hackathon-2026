FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 저장소 구조(backend/app)를 그대로 따라야 config.py 의 경로 계산이 맞습니다
WORKDIR /srv/backend

# root로 돌리지 않습니다. 작업 폴더는 SQLite 파일을 쓸 수 있게 app 사용자에게 줍니다
RUN useradd --system --create-home --uid 10001 app \
    && chown app:app /srv/backend

# 의존성을 코드보다 먼저 설치해, 코드만 바뀌면 이 층은 캐시를 다시 씁니다
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# compose watch 가 이 폴더에 파일을 덮어쓰므로 app 사용자 소유여야 합니다
COPY --chown=app:app app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

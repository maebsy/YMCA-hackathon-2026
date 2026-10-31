# 72hours 프론트엔드

홈의 웹사이트 URL 입력은 고정 샘플을 보여주는 체험입니다. 입력한 사이트에 접속하거나 해당 사이트의 보안을 검사하지 않습니다. 실제 공개 GitHub 저장소 검사는 `/repository`에서 기존 엔진 API로 실행합니다.

## 실행

Node.js와 npm을 설치한 뒤 이 디렉터리에서 실행합니다.

```bash
npm ci
npm run dev -- --port 3004
```

http://localhost:3004 에서 확인할 수 있습니다. Production 실행은 `npm run build` 후 `npm run start -- --port 3004`를 사용합니다.

`/api/*`는 기본적으로 `http://127.0.0.1:8000/api/*`로 전달됩니다. 다른 백엔드를 사용하면 `.env.local`의 `BACKEND_ORIGIN`을 설정합니다. 실제 검사는 실행 중인 백엔드가 필요하며, 추가 AI 해석을 사용할 수 없어도 엔진 결과를 유지합니다.

## 화면과 상태

- `/` → `/scan` → `/findings` → `/repair/[id]` → `/report`: URL 입력부터 수정 안내·리포트까지의 샘플 흐름.
- `/repository`: 공개 GitHub 검사, 진행 로그, 발견 항목과 상세, 재검사, 실제 HTML/Markdown 리포트.
- `/incident`: 직접 확인한 사실을 입력하고 편집하는 초안. 외부 신고는 제출하지 않습니다.
- `/help`: 샘플과 실제 검사 범위, 사용 방법.

샘플 입력과 조치 상태, 사고 초안은 화면 이동 동안 유지되며 새로고침하면 초기화됩니다. 실제 마지막 검사 결과와 수동 조치 표시는 브라우저에 저장·복원됩니다. 수동 조치는 재검증 대기이며 엔진의 `code_resolved` 상태만 해결 확인으로 표시합니다.

헤더·본문·푸터는 공통 최대 폭 748px를 사용합니다. 수정 안내·사고 기록·도움말과 실제 발견 목록/상세는 한 열로 배치합니다. 기존 전역 색상·폰트·칩을 재사용하고 새 흐름 CSS의 scope 경계로 기존 컴포넌트와 스타일을 구분합니다.

## 검증

```bash
npm run lint
npm run typecheck
npm run test:domain
npm run test:integration
npm run build
```

도메인 검사는 URL 입력·샘플 정체성·조치 상태를, 통합 검사는 API·저장 복원 계약과 실제 provider의 상태 흐름을 확인합니다. 통합 검사의 API 응답은 fixture이므로 외부 저장소 실제 검사나 브라우저 검증을 대신하지 않습니다. 실제 엔진·추가 AI·리포트 서버 연결은 별도로 확인해야 합니다.

Tailwind CSS는 설치된 `@tailwindcss/turbopack` 로더로 빌드합니다. Google Fonts 연결 실패 시 시스템 폰트를 사용합니다. CSS `@scope`를 지원하지 않는 구형 브라우저는 별도 호환성 검증이 필요합니다.

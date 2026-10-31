# GitHub 로그인

Supabase Auth의 GitHub 공급자에 GitHub App의 Client ID·Secret을 연결하는 로그인 작업입니다.

- 프런트 설정이 없으면 로그인 UI와 인증 헤더를 추가하지 않고 기존 검사 흐름을 유지합니다.
- 이번 범위는 로그인·로그아웃·상태 표시와 내부 API의 Supabase Bearer 토큰 전달입니다.
- 저장소 소유권 확인, provider_token 저장, 사용자 저장소 실검증 활성화는 다음 단계입니다.
- `SCAN_REQUIRE_AUTH` 기본값은 바꾸지 않습니다.

설정 절차와 검증 결과는 구현 및 공식 문서 확인 후 이 초안에 보완합니다.

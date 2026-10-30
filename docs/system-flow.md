# 72hours 시스템 플로우

취약점 발견부터 해결, 리포트 전달까지 72시간 안에 끝내는 웹사이트 보안 서비스입니다.

> 같은 내용을 그림으로 보려면 [`system-flow.html`](system-flow.html)을 내려받아 브라우저로 여세요.

## 1. 사용자 흐름

```mermaid
flowchart LR
    A["① 연결<br/>GitHub · CLI"] --> B["② 검사<br/>이후 매일 지속 검사"]
    B --> C["③ 알림<br/>새 취약점이 나오면"]
    C --> D["④ 대응 안내<br/>쉬운 설명 + 수정 지시"]
    D --> E["⑤ 재검사·리포트<br/>통과하면 완료 리포트"]
    E -- 수정 후 반복 --> B
```

- 핵심은 ④입니다. 비개발자도 이해하고 바로 고칠 수 있게 안내합니다.
- **72시간 타이머**: ②에서 취약점이 발견된 순간(0h) 시작하고, ⑤에서 재검사를 통과해 완료 리포트가 전달되면(72h) 멈춥니다.

## 2. 시스템 구성

```mermaid
flowchart LR
    subgraph S1["① 연결"]
        GH["GitHub App<br/>기본 · 읽기 전용"]
        CLI["CLI<br/>GitHub 없이 업로드"]
    end

    subgraph S2["② 검사 · 우리 서버"]
        COL["수집<br/>임시 폴더 · 검사 후 삭제"]
        OG["Opengrep<br/>코드 · 우리 규칙"]
        OSV["OSV-Scanner<br/>라이브러리"]
        GL["Gitleaks<br/>비밀키"]
        OWN["자체 검사기<br/>설정 실수"]
        NORM["결과 정리 · 우선순위"]
        COL --> OG & OSV & GL & OWN --> NORM
    end

    subgraph S3["③ 해석 · GPU"]
        BLUE["Blue<br/>설명 · 수정 지시"]
        RED["Red<br/>공격해서 검증"]
        BLUE --> RED
        RED -- 실패 시 다시 --> BLUE
    end

    subgraph S4["④ 전달 · 사용자"]
        DASH["웹 대시보드<br/>설명 · 수정 지시 · 72시간 타이머"]
        MCP["MCP 전달"]
        COPY["복사"]
        USER["사용자 · AI 코딩툴<br/>Cursor · Claude Code · Codex"]
        DASH --> MCP & COPY --> USER
    end

    GH & CLI --> COL
    NORM --> BLUE
    RED -- 통과한 것만 --> DASH

    subgraph KEEP["매일 지키기"]
        SCH["스케줄러<br/>매일 새 CVE 대조"]
        DB["DB<br/>결과 · 조치 기록 · 타이머"]
        ALERT["알림<br/>이메일 · 재알림"]
    end

    NORM --> DB
    RED --> DB
    DB --> SCH --> COL
    DB -- 새 취약점 --> ALERT --> USER

    subgraph OUT["72시간 산출물"]
        REPORT["완료 리포트<br/>해결 확인 후 전달"]
        FILING["신고서 작성 서포트<br/>24h 침해사고 · 72h 개인정보 유출"]
    end

    DB --> REPORT
    REPORT -- 사고 의심 시 --> FILING
    USER -- "⑤ 재검사" --> COL
```

- 연결 방식의 확장 후보는 CI(GitHub Actions에서 CLI 실행)와 MCP 모드입니다.
- 소스는 검사가 끝나면 지우고, 결과와 의존성 목록만 남깁니다.

## 3. 핵심 네 가지

| 구분 | 내용 |
|---|---|
| **찾기** · 검증된 도구 + 우리 규칙 | 코드, 라이브러리, 비밀키(과거 커밋 포함), 웹셸, 설정 실수를 찾습니다. 모두 유료 서비스에 써도 되는 라이선스입니다. |
| **고치기** · GPU LLM Red–Blue | Blue가 쉬운 설명과 수정 지시를 쓰고 Red가 공격해 봅니다. 통과한 수정만 대시보드와 MCP로 코딩툴에 전달합니다. |
| **72시간** · 해결 + 리포트, 사고 시 신고 서포트 | 발견 순간 타이머가 시작되고 완료 리포트 전달로 멈춥니다. 사고가 의심되면 24시간·72시간 신고서 작성을 돕습니다. |
| **증명** · GPU 효과를 숫자로 | 같은 취약점을 스캐너 원문, GPU 없는 LLM, GPU LLM, Red–Blue 추가로 처리해 조치 성공률과 이해도를 비교합니다. |

## 4. 팀과 확정할 것

- [ ] 공통 JSON 규격과 검사 실행 방식 (오늘 밤, 전원)
- [ ] 우리 규칙 목록 (장양환) · GPU 모델과 Red–Blue 횟수 (김건우)
- [ ] 신고서 작성 서포트를 MVP에 넣을지 (전원)
- [ ] 신고서 서식과 신고 대상 기준 원문 확인 (박기태)

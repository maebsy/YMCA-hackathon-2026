"use strict";
for (const [button, field] of [["copy-request", "request"], ["copy-url", "endpoint"]]) {
  document.getElementById(button).addEventListener("click", async () => {
    const input = document.getElementById(field);
    try {
      await navigator.clipboard.writeText(input.value);
      document.getElementById("notice").textContent = field === "endpoint" ? "서버 URL을 복사했습니다. AI 앱의 MCP 서버 URL 칸에 붙여 넣으세요." : "연결 확인 문장을 복사했습니다. 72hours를 활성화한 AI 대화에 붙여 넣으세요.";
    } catch {
      input.focus(); input.select();
      document.getElementById("notice").textContent = "자동 복사가 차단되어 내용을 선택했습니다. 직접 복사해 주세요.";
    }
  });
}

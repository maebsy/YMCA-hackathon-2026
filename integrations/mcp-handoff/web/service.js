"use strict";
for (const [button, field] of [["copy-request", "request"], ["copy-url", "endpoint"]]) {
  document.getElementById(button).addEventListener("click", async () => {
    const input = document.getElementById(field);
    try {
      await navigator.clipboard.writeText(input.value);
      document.getElementById("notice").textContent = "복사했습니다. AI 에이전트 대화에 붙여 넣으세요.";
    } catch {
      input.focus(); input.select();
      document.getElementById("notice").textContent = "자동 복사가 차단되어 문장을 선택했습니다. 복사해서 AI에게 보내세요.";
    }
  });
}

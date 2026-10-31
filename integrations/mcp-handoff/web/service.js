"use strict";
document.getElementById("copy-url").addEventListener("click", async () => {
  const input = document.getElementById("endpoint");
  const notice = document.getElementById("notice");
  try {
    await navigator.clipboard.writeText(input.value);
    notice.textContent = "서버 URL을 복사했습니다. AI 앱의 MCP 서버 추가에 붙여 넣으세요.";
  } catch {
    input.focus(); input.select();
    notice.textContent = "자동 복사가 차단되어 주소를 선택했습니다. 직접 복사해 주세요.";
  }
});

"use strict";
const STORE = "72hours:last-scan:v1", LINKS = "72hours:mcp-links:v1";
const $ = id => document.getElementById(id);
let selection = null, busy = false, links = [];
const notify = text => { $("notice").textContent = text; };

function exportedScan() {
  const saved = JSON.parse(localStorage.getItem(STORE) || "null");
  const scan = saved?.result, target = scan?.target;
  const match = /^https:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)\/?$/.exec(target?.repo_url || "");
  if (!match || !/^[a-f0-9]{40}$/i.test(target.commit_sha || "") || !/^[a-f0-9]{32}$/.test(scan.scan_id || "")) {
    throw new Error("실제 검사 결과가 없습니다. 같은 브라우저의 웹 검사 화면에서 검사를 먼저 진행해 주세요.");
  }
  if (saved.repoUrl !== target.repo_url || saved.reportInput?.scan?.repo !== target.repo_url) {
    throw new Error("검사 대상 정보가 일치하지 않습니다. 웹에서 결과를 다시 확인해 주세요.");
  }
  const known = new Set((scan.findings || []).map(f => f.fingerprint));
  const raw = saved.reportInput?.explain_results;
  const results = (Array.isArray(raw) ? raw : []).slice(0, 50).map(r => {
    const e = r.explanation;
    const result = {fingerprint:r.fingerprint, status:r.status, covers:r.covers || []};
    if (e) {
      result.explanation = {};
      for (const key of ["fingerprint","variant","red_verdict","needs_manual_review","false_positive_suspect","ai_fix_prompt","model","prompt_version"])
        result.explanation[key] = e[key];
      const last = Array.isArray(e.red_rounds) ? e.red_rounds.at(-1) : null;
      if (last) result.explanation.red_rounds = [{verdict:last.verdict, issues:Array.isArray(last.issues) && !last.issues.length ? [] : ["review_required"]}];
    }
    return result;
  });
  const used = new Set(results.flatMap(r => [r.fingerprint, ...r.covers]).filter(fp => known.has(fp)));
  return {scan:{repository:`${match[1]}/${match[2].replace(/\.git$/, "")}`, revision:target.commit_sha.toLowerCase(),
    scan_id:scan.scan_id, scanned_at:scan.scanned_at, fingerprints:[...used]}, results};
}

function ready(result) {
  const e = result.explanation, last = e?.red_rounds?.at(-1);
  return result.status === "done" && e?.fingerprint === result.fingerprint && e.variant === "D" &&
    e.red_verdict === "pass" && last?.verdict === "pass" && Array.isArray(last.issues) && !last.issues.length &&
    e.needs_manual_review === false && e.false_positive_suspect === false &&
    typeof e.ai_fix_prompt === "string" && e.ai_fix_prompt.trim() && e.ai_fix_prompt.length <= 2000 &&
    typeof e.model === "string" && e.model.trim() && typeof e.prompt_version === "string" && e.prompt_version.trim();
}

function refresh() {
  try {
    selection = exportedScan();
    const source = selection.scan, count = selection.results.filter(ready).length;
    $("summary").textContent = `${source.repository} · ${source.revision.slice(0,12)} · 검사 ${source.scan_id} · ${source.scanned_at}`;
    $("counts").textContent = `현재 LLM 결과 ${selection.results.length}건 / 전달 가능 ${count}건. ${count ? "선택한 검사 결과로 연결을 만들 수 있습니다." : "Red 통과 해석을 기다리거나 수동 확인 항목을 확인해 주세요."}`;
    $("issue").disabled = busy || count === 0;
  } catch (error) {
    selection = null;
    $("summary").textContent = error.message;
    $("counts").textContent = "이 화면은 공용 샘플을 대신 연결하지 않습니다.";
    $("issue").disabled = true;
  }
}

function remember() {
  try { localStorage.setItem(LINKS, JSON.stringify(links)); }
  catch { notify("브라우저 저장에 실패했습니다. 이 화면을 닫기 전에 요청을 복사하거나 연결을 폐기하세요."); }
}

function showLinks(index = 0) {
  $("delivery").hidden = links.length === 0;
  $("connections").replaceChildren();
  links.forEach((link, i) => {
    const option = document.createElement("option");
    option.value = String(i); option.textContent = `${link.source.repository} · ${link.source.scan_id.slice(0,8)} · ${link.expires_at}`;
    $("connections").append(option);
  });
  $("connections").value = String(index);
  selectLink();
}

function selectLink() {
  const link = links[Number($("connections").value)];
  if (!link) return;
  const expired = Date.parse(link.expires_at) <= Date.now();
  $("identity").textContent = `${link.source.repository} @ ${link.source.revision.slice(0,12)} · 전달 ${link.findings.filter(f => f.ready).length}건 · ${expired ? "만료됨" : "24시간 내 사용 가능"}`;
  $("request").value = `${link.guide_url}\n이 안내를 읽고 내 AI 도구에 72hours MCP를 연결해 줘. list_findings로 검사 대상과 커밋을 내 작업 저장소와 확인하고, ready=true 항목의 get_fix_prompt를 받아 관련 코드를 수정해 줘. 기존 변경은 보존하고 기능·보안 테스트와 재검사 결과를 알려줘. 대상이 다르면 수정하지 마. 이 비밀 연결은 코드나 공개 문서에 저장하지 마.`;
  $("copy").disabled = expired;
}

$("issue").onclick = async () => {
  if (busy || !selection) return;
  let current;
  try { current = exportedScan(); } catch (error) { notify(error.message); refresh(); return; }
  if (current.scan.scan_id !== selection.scan.scan_id || current.scan.revision !== selection.scan.revision) {
    refresh(); notify("검사 대상이 바뀌었습니다. 표시된 대상을 확인하고 다시 눌러 주세요."); return;
  }
  if (links.length >= 20) { notify("보관한 연결이 20개입니다. 사용하지 않는 연결을 먼저 폐기하세요."); return; }
  busy = true; refresh(); notify("선택한 결과로 전용 연결을 만들고 있습니다.");
  try {
    const response = await fetch("/mcp/links", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(current)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "연결 발급에 실패했습니다.");
    links.unshift(data); remember(); showLinks(); notify("내 검사 전용 연결이 만들어졌습니다. 아래 수정 요청을 복사해 주세요.");
  } catch (error) { notify(error.message); }
  finally { busy = false; refresh(); }
};
$("copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("request").value); notify("수정 요청을 복사했습니다. 본인의 AI 에이전트에게 전달해 주세요."); }
  catch { $("request").select(); notify("복사 권한이 없습니다. 선택된 문장을 직접 복사해 주세요."); }
};
$("revoke").onclick = async () => {
  const index = Number($("connections").value), link = links[index];
  if (!link) return;
  $("revoke").disabled = true;
  try {
    const response = await fetch("/mcp/links/revoke", {method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:link.token,revoke_token:link.revoke_token})});
    if (!response.ok && response.status !== 404) throw new Error("폐기에 실패했습니다. 다시 시도해 주세요.");
    links.splice(index, 1); remember(); showLinks(); notify("연결을 폐기했습니다. 해당 주소로는 더 이상 결과를 읽을 수 없습니다.");
  } catch (error) { notify(error.message); }
  finally { $("revoke").disabled = false; }
};
$("refresh").onclick = refresh;
$("connections").onchange = selectLink;
window.addEventListener("storage", event => { if (event.key === STORE) refresh(); });
try {
  const savedLinks = JSON.parse(localStorage.getItem(LINKS) || "[]");
  if (Array.isArray(savedLinks)) links = savedLinks.filter(x => x?.source && Array.isArray(x.findings) &&
    typeof x.token === "string" && typeof x.guide_url === "string" && x.guide_url.startsWith("https://") &&
    // 안내 주소는 대표(고정) 주소로 만들어지므로, 다른 허용 주소에서 연 화면이어도 같은 연결로 봅니다 (#136)
    x.guide_url.endsWith(`/mcp/h/${x.token}/agent.txt`)).slice(0,20);
} catch { /* Storage may be unavailable. No synthetic data fallback. */ }
showLinks(); refresh();

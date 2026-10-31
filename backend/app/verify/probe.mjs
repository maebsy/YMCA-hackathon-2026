// 샌드박스 안에서 한 상태(수정 전 또는 후)를 점검하는 probe.
// 하는 일: npm start 로 앱을 띄우고 → attacks.json 의 HTTP 요청을 그대로 보내 success_when 판정 →
//          앱을 끄고 → npm test 로 기능 보존 확인 → 결과 JSON을 stdout에 출력.
// 공격은 미리 정의된 요청의 '재생'입니다(회귀 테스트). 새 공격을 만들지 않습니다.
// 네트워크 없이 127.0.0.1 만 씁니다 → Docker --network none 안에서도 그대로 동작합니다.
//
// 입력(stdin, JSON): { attacks, port?, startCmd?, testCmd?, startTimeoutMs?, runTests? }
// 출력(stdout, JSON): { reachable, attacks:[{id, succeeded, status, evidence}], tests:{ok, passed, failed} }
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { networkInterfaces } from "node:os";

function readStdin() {
  return new Promise((resolve) => {
    let b = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (b += c));
    process.stdin.on("end", () => resolve(b));
  });
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    const p = spawn(cmd, args, { ...opts });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => resolve({ code, out, err }));
    p.on("error", (e) => resolve({ code: -1, out, err: String(e) }));
  });
}

async function waitForPort(base, timeoutMs) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    try {
      const r = await fetch(base, { signal: AbortSignal.timeout(1500) });
      if (r.status > 0) return true;
    } catch {
      /* 아직 안 뜸 */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

function buildUrl(base, req) {
  const u = new URL(req.path || "/", base);
  for (const [k, v] of Object.entries(req.query || {})) u.searchParams.set(k, v);
  return u.toString();
}

async function send(base, req) {
  const res = await fetch(buildUrl(base, req), {
    method: req.method || "GET",
    headers: req.headers || {},
    body: req.body,
    redirect: "manual",
    signal: AbortSignal.timeout(8000),
  });
  const text = await res.text();
  return { status: res.status, text };
}

// success_when: "json_array_len_gte:N" | "body_contains:STR" | "status_eq:N"
function judge(rule, resp) {
  const [kind, ...rest] = (rule || "").split(":");
  const arg = rest.join(":");
  if (kind === "json_array_len_gte") {
    try {
      const a = JSON.parse(resp.text);
      return Array.isArray(a) && a.length >= Number(arg);
    } catch {
      return false;
    }
  }
  if (kind === "body_contains") return resp.text.includes(arg);
  if (kind === "status_eq") return resp.status === Number(arg);
  return false;
}

function parseTapCounts(out) {
  const pass = /# pass (\d+)/.exec(out);
  const fail = /# fail (\d+)/.exec(out);
  return { passed: pass ? Number(pass[1]) : null, failed: fail ? Number(fail[1]) : null };
}

// 격리 자체 점검: 외부로 아무 요청도 보내지 않고, 지금 이 프로세스가 놓인 환경만 읽습니다.
//  - network_isolated: 루프백(lo) 말고 네트워크 장치가 없음 (Docker --network none 이면 true)
//  - non_root: root(uid 0)가 아님
//  - caps_dropped: 리눅스 특수 권한(CapEff)이 0
//  - no_new_privs: 권한 상승 금지(no-new-privileges)가 켜짐
function isolationCheck() {
  const ifaces = Object.entries(networkInterfaces())
    .filter(([, addrs]) => (addrs || []).some((a) => !a.internal))
    .map(([name]) => name);
  let capEff = null, noNewPrivs = null;
  try {
    const st = readFileSync("/proc/self/status", "utf8");
    const cap = /^CapEff:\s*([0-9a-f]+)/m.exec(st);
    const nnp = /^NoNewPrivs:\s*(\d)/m.exec(st);
    capEff = cap ? cap[1] : null;
    noNewPrivs = nnp ? nnp[1] === "1" : null;
  } catch {
    /* 리눅스가 아님 */
  }
  const uid = typeof process.getuid === "function" ? process.getuid() : null;
  return {
    network_isolated: ifaces.length === 0,
    external_interfaces: ifaces,
    non_root: uid === null ? null : uid !== 0,
    caps_dropped: capEff === null ? null : /^0+$/.test(capEff),
    no_new_privs: noNewPrivs,
  };
}

async function main() {
  const cfg = JSON.parse((await readStdin()) || "{}");
  // 워치독: 어떤 경우에도 probe가 영원히 멈추지 않게 (기본 90초)
  const watchdog = setTimeout(() => {
    process.stdout.write(JSON.stringify({ reachable: false, appError: "probe timeout", attacks: [], tests: { ok: null, passed: null, failed: null } }));
    process.exit(0);
  }, cfg.hardTimeoutMs || 90000);
  watchdog.unref();
  const port = cfg.port || 3100;
  const base = `http://127.0.0.1:${port}`;
  const startCmd = cfg.startCmd || ["npm", "start"];
  const cwd = cfg.cwd || process.cwd();
  const env = { ...process.env, PORT: String(port), HOST: "127.0.0.1" };

  // detached: npm start 가 자식 node 를 띄워도 프로세스 그룹째 죽일 수 있게 (안 그러면 서버가 살아남음)
  const app = spawn(startCmd[0], startCmd.slice(1), { cwd, env, detached: true });
  let appErr = "";
  app.stderr.on("data", (d) => (appErr += d));
  app.stdout.on("data", () => {});
  const killApp = () => {
    try {
      process.kill(-app.pid, "SIGKILL");
    } catch {
      try {
        app.kill("SIGKILL");
      } catch {
        /* 이미 종료 */
      }
    }
  };

  const reachable = await waitForPort(base, cfg.startTimeoutMs || 15000);
  const results = [];
  if (reachable) {
    for (const atk of cfg.attacks || []) {
      if (!atk.runtime) continue;
      try {
        const resp = await send(base, atk.request);
        results.push({
          id: atk.id,
          succeeded: judge(atk.success_when, resp),
          status: resp.status,
          evidence: resp.text.slice(0, 200),
        });
      } catch (e) {
        results.push({ id: atk.id, succeeded: false, status: 0, evidence: `error: ${String(e).slice(0, 120)}` });
      }
    }
  }

  killApp();
  await new Promise((r) => setTimeout(r, 300));

  let tests = { ok: null, passed: null, failed: null };
  if (cfg.runTests !== false) {
    const testCmd = cfg.testCmd || ["npm", "test"];
    const t = await run(testCmd[0], testCmd.slice(1), { cwd, env });
    const counts = parseTapCounts(t.out + t.err);
    tests = { ok: t.code === 0, passed: counts.passed, failed: counts.failed };
  }

  clearTimeout(watchdog);
  process.stdout.write(JSON.stringify({ reachable, appError: reachable ? "" : appErr.slice(0, 300), attacks: results, tests, isolation: isolationCheck() }));
}

main();

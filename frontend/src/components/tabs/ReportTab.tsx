"use client";

import React, { useState } from "react";
import { AlertTriangle, Copy, Play } from "lucide-react";
import { mockApiPayloads } from "@/data/mockData";
import { plainReport } from "@/lib/api";

interface ReportTabProps {
  // 실제 검사 결과로 만든 리포트 입력 (없으면 아직 검사 전)
  reportInput?: unknown;
  onShowToast: (msg: string) => void;
  onOpenLoginModal: () => void;
}

export const ReportTab: React.FC<ReportTabProps> = ({
  reportInput,
  onShowToast,
  onOpenLoginModal,
}) => {
  const [llmDegraded, setLlmDegraded] = useState(false);
  const [zapRunning, setZapRunning] = useState(false);
  const [zapBeforeStatus, setZapBeforeStatus] = useState("STATUS: 200 OK (뚫림 ⚠)");
  const [zapBeforeLog, setZapBeforeLog] = useState(
    "GET /api/orders?orderId=' OR '1'='1 HTTP/1.1\nHost: demo-order-site.local\n\n→ Response: 120건 전체 고객 주문 JSON 노출됨"
  );
  const [zapAfterStatus, setZapAfterStatus] = useState(
    "STATUS: 400 BLOCKED (방어 성공 ✓)"
  );
  const [zapAfterLog, setZapAfterLog] = useState(
    'GET /api/orders?orderId=\' OR \'1\'=\'1 HTTP/1.1\nHost: demo-order-site.local\n\n→ Response: {"error": "Invalid orderId parameter"} (유출 0건)'
  );
  const [apiPreviewText, setApiPreviewText] = useState<string | null>(null);
  const [realHtml, setRealHtml] = useState<string | null>(null);
  const [realLoading, setRealLoading] = useState(false);

  const makeRealReport = async () => {
    if (!reportInput) return;
    setRealLoading(true);
    try {
      setRealHtml(await plainReport(reportInput, "html"));
    } catch (e) {
      onShowToast(String((e as Error)?.message || e));
    } finally {
      setRealLoading(false);
    }
  };

  const copyRealMarkdown = async () => {
    if (!reportInput) return;
    try {
      await navigator.clipboard.writeText(await plainReport(reportInput, "markdown"));
      onShowToast("실제 검사 리포트(Markdown)를 복사했습니다.");
    } catch (e) {
      onShowToast(String((e as Error)?.message || e));
    }
  };

  const runZapDemo = () => {
    setZapRunning(true);
    setZapBeforeLog("ZAP Active Scan 요청 전송 중...");
    setZapAfterLog("패치 적용 브랜치에 동일 페이로드 전송 중...");

    setTimeout(() => {
      setZapBeforeStatus("STATUS: 200 OK (뚫림 ⚠)");
      setZapBeforeLog(
        "GET /api/orders?orderId=' OR '1'='1 HTTP/1.1\nHost: demo-order-site.local\n\n→ Response: 120건 전체 고객 주문 JSON 노출됨"
      );
      setZapAfterStatus("STATUS: 400 BLOCKED (방어 성공 ✓)");
      setZapAfterLog(
        'GET /api/orders?orderId=\' OR \'1\'=\'1 HTTP/1.1\nHost: demo-order-site.local\n\n→ Response: {"error": "Invalid orderId parameter"} (유출 0건)'
      );
      setZapRunning(false);
      onShowToast("공격 재현 시뮬레이션이 끝났습니다. 실제 공격·방어 검증은 수행하지 않았습니다.");
    }, 700);
  };

  const copyReportMarkdown = async () => {
    const md = `# 72hours 완료 리포트 예제 (Scan #41)
> 데모 데이터입니다. 실제 검사·패치·재검사·OWASP ZAP 검증을 수행한 기록이 아니며, 보안 조치 증빙으로 사용할 수 없습니다.
- 대상 저장소: https://github.com/minji-cafe/order-site
- 발견 일시: 2026-10-31 05:42 KST
- 해결 소요 시간 예시: 10시간 47분 / 72시간 기한 내 완료
- 실제 조치 및 검증 상태: 미검증 (아래 화면의 완료·방어·미검사 수치는 예제이며 현재 취약점 상태와 연동되지 않습니다.)`;
    try {
      await navigator.clipboard.writeText(md);
      onShowToast("예제 리포트(Markdown)가 복사되었습니다. 실제 검증 증빙이 아닙니다.");
    } catch {
      onShowToast("복사에 실패했습니다. 클립보드 권한을 확인한 뒤 다시 시도해 주세요.");
    }
  };

  const handleTestApi = (type: "auth" | "poll" | "explain" | "report") => {
    if (type === "auth") {
      onOpenLoginModal();
      return;
    }
    const payload = mockApiPayloads[type];
    setApiPreviewText(
      `// Response from /api/${type}\n` + JSON.stringify(payload, null, 2)
    );
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <section className="rounded-xl border border-[#27272a] bg-[#0f0f10] p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-[#fafafa]">실제 검사 리포트 (POST /api/reports/plain)</h2>
          <div className="flex gap-2">
            <button
              onClick={makeRealReport}
              disabled={!reportInput || realLoading}
              className="px-3 py-1.5 rounded bg-[#18181b] border border-[#27272a] text-sm text-[#fafafa] disabled:opacity-50 cursor-pointer"
            >
              {realLoading ? "만드는 중..." : "리포트 만들기"}
            </button>
            <button
              onClick={copyRealMarkdown}
              disabled={!reportInput}
              className="px-3 py-1.5 rounded bg-[#18181b] border border-[#27272a] text-sm text-[#fafafa] disabled:opacity-50 cursor-pointer"
            >
              Markdown 복사
            </button>
          </div>
        </div>
        {!reportInput && (
          <p className="text-sm text-[#a1a1aa]">워크스페이스에서 저장소를 검사하면 그 결과로 리포트를 만들 수 있습니다.</p>
        )}
        {realHtml && (
          <iframe
            title="실제 검사 리포트"
            srcDoc={realHtml}
            sandbox=""
            className="w-full h-[640px] rounded-lg bg-white"
          />
        )}
      </section>
      <p className="rounded-lg border border-[#ff9f43]/50 bg-[#ff9f43]/10 p-4 text-sm text-[#ff9f43]">
        예제 리포트 · 아래 완료 시간, 패치·검증 결과, 미검사 영역 수와 ZAP 응답은 고정 데모 데이터입니다.
        현재 워크스페이스의 해결 상태와 연동되지 않으며 실제 보안 조치 증빙이 아닙니다.
      </p>
      {/* LLM 서버 상태 시뮬레이션 배너 */}
      {llmDegraded && (
        <div className="p-3.5 rounded-lg bg-[#ff9f43]/15 border border-[#ff9f43] text-[#ff9f43] font-mono text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              <b>[GET /api/llm/health : DEGRADED]</b> 현재 GPU LLM 서버 요청이
              많아 해석이 늦어지고 있습니다. 스캐너 원문 결과는 먼저 확인하실 수
              있습니다.
            </span>
          </div>
          <button
            onClick={() => {
              setLlmDegraded(false);
              onShowToast("GPU LLM 서버 상태가 ONLINE으로 복구되었습니다.");
            }}
            className="px-2.5 py-1 rounded bg-[#ff9f43] text-black font-bold cursor-pointer"
          >
            정상 복구
          </button>
        </div>
      )}

      {/* 1. 72시간 완료 리포트 */}
      <div className="bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden">
        <div className="chrome-bar justify-between">
          <div className="flex items-center gap-2">
            <div className="dots">
              <i />
              <i />
              <i />
            </div>
            <span className="font-mono text-xs text-[#a1a1aa] ml-2">
              POST /api/reports/plain — Example Completion Report (#41)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setLlmDegraded(!llmDegraded)}
              className="px-2.5 py-1 rounded bg-[#18181b] border border-[#27272a] font-mono text-[11px] text-[#a1a1aa] hover:text-white cursor-pointer"
            >
              ⚡ LLM 지연 배너 테스트
            </button>
            <button
              onClick={copyReportMarkdown}
              className="px-3 py-1 rounded bg-[#d4ff3a] text-black font-mono text-xs font-bold hover:brightness-110 transition flex items-center gap-1 cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>↓ 예제 리포트 Markdown 복사</span>
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#27272a] pb-5">
            <div>
              <span className="font-mono text-xs text-[#d4ff3a] uppercase">
                ⑤ EXAMPLE COMPLETION REPORT · NOT VERIFIED
              </span>
              <h3 className="font-mono text-2xl font-bold text-white mt-1">
                72시간 완료 리포트 예제 (minji-cafe/order-site)
              </h3>
              <p className="text-sm text-[#a1a1aa] mt-1">
                평소에는 보안 조치를 끝냈다는 증빙 기록이 되며, 실제 침해사고
                발생 시 정보통신망법 신고 항목에 그대로 옮겨 적을 수 있는 준비
                자료입니다.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-[#0a0a0a] border border-[#d4ff3a]/50 font-mono text-right shrink-0">
              <span className="text-[11px] text-[#a1a1aa] block">
                발견부터 해결·전달까지 총 소요 시간
              </span>
              <b className="text-2xl text-[#d4ff3a]">10시간 47분</b>
              <span className="text-xs text-[#a1a1aa]">
                {" "}
                / 72시간 기한 내 완료
              </span>
            </div>
          </div>

          {/* 7개 표준 항목 테이블 */}
          <div className="overflow-x-auto border border-[#27272a] rounded-lg">
            <table className="w-full text-left font-mono text-xs">
              <thead className="bg-[#0a0a0a] text-[#a1a1aa] border-b border-[#27272a]">
                <tr>
                  <th className="p-3.5 w-40">리포트 항목</th>
                  <th className="p-3.5">상세 기록 내용 (Scan #41 기준)</th>
                  <th className="p-3.5 w-36">침해사고 신고 매핑</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#27272a] text-[#fafafa]">
                <tr>
                  <td className="p-3.5 font-bold">발견 일시·경로</td>
                  <td className="p-3.5">
                    2026-10-31 05:42 KST · 첫 전체 검사 (GitHub App 연결)
                  </td>
                  <td className="p-3.5">
                    <span className="px-2 py-0.5 rounded bg-[#18181b] border border-[#27272a] text-[#d4ff3a]">
                      발생 일시
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-3.5 font-bold">원인</td>
                  <td className="p-3.5 leading-relaxed">
                    • <code>src/lib/supabase.ts:4</code> 관리자 키 노출
                    (gitleaks)
                    <br />• <code>src/app/api/orders/route.ts:9</code> SQL
                    Injection (CWE-89)
                    <br />• <code>supabase/migrations/20261001_init.sql</code> RLS
                    미설정
                  </td>
                  <td className="p-3.5">
                    <span className="px-2 py-0.5 rounded bg-[#18181b] border border-[#27272a] text-[#d4ff3a]">
                      원인
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-3.5 font-bold">영향 범위</td>
                  <td className="p-3.5 leading-relaxed">
                    고객 주문 테이블(이메일, 연락처, 주소) 무단 열람 가능 · Red
                    시나리오: 자동 수집 봇의 키 탈취 및 SQL 우회
                  </td>
                  <td className="p-3.5">
                    <span className="px-2 py-0.5 rounded bg-[#18181b] border border-[#27272a] text-[#d4ff3a]">
                      피해 내용
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-3.5 font-bold">조치 내용</td>
                  <td className="p-3.5 leading-relaxed">
                    기존 <code>service_role</code> 키 폐기 및 재발급, 서버
                    환경변수 분리, SQL 파라미터 바인딩, RLS 정책 활성화
                  </td>
                  <td className="p-3.5">
                    <span className="px-2 py-0.5 rounded bg-[#18181b] border border-[#27272a] text-[#d4ff3a]">
                      대응 현황
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-3.5 font-bold">검증 결과</td>
                  <td className="p-3.5 text-[#d4ff3a] font-bold">
                    ✓ 재검사 스캐너 통과 + 데모 사이트 실제 공격 재현(OWASP ZAP)
                    차단 확인
                  </td>
                  <td className="p-3.5">
                    <span className="px-2 py-0.5 rounded bg-[#18181b] border border-[#27272a] text-[#d4ff3a]">
                      대응 현황
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-3.5 font-bold">검사 못 한 영역</td>
                  <td className="p-3.5">
                    <span className="text-[#d4ff3a]">0곳</span> (모든 파일 및
                    의존성 트리 정상 스캔 완료 — #28 규격 준수)
                  </td>
                  <td className="p-3.5 text-[#a1a1aa]">-</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* 실제 공격 Red (데모 사이트 OWASP ZAP 시뮬레이터) */}
          <div className="p-5 rounded-xl bg-[#0a0a0a] border border-[#27272a] space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-mono text-xs text-[#ff5f56] font-bold">
                  ● 공격 재현 시뮬레이션 (실제 ZAP 실행 아님)
                </span>
                <h4 className="font-mono text-base font-bold text-white mt-0.5">
                  수정 전·후 공격 응답 예시 비교
                </h4>
              </div>
              <button
                onClick={runZapDemo}
                disabled={zapRunning}
                className="px-3.5 py-1.5 rounded bg-[#ff5f56] text-white font-mono text-xs font-bold hover:brightness-110 transition cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>
                  {zapRunning ? "공격 페이로드 전송 중..." : "▶ 수정 전·후 공격 재현 실행"}
                </span>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
              <div className="p-4 rounded-lg bg-[#111113] border border-[#ff5f56]/40 space-y-2">
                <div className="flex justify-between text-[#ff5f56] font-bold">
                  <span>[BEFORE FIX] 수정 전 공격 요청</span>
                  <span>{zapBeforeStatus}</span>
                </div>
                <pre className="text-[#a1a1aa] whitespace-pre-wrap">
                  {zapBeforeLog}
                </pre>
              </div>

              <div className="p-4 rounded-lg bg-[#111113] border border-[#d4ff3a]/40 space-y-2">
                <div className="flex justify-between text-[#d4ff3a] font-bold">
                  <span>[AFTER FIX] ④ 가이드 적용 후 동일 공격</span>
                  <span>{zapAfterStatus}</span>
                </div>
                <pre className="text-[#fafafa] whitespace-pre-wrap">
                  {zapAfterLog}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 2. 백엔드 API 핸드오프 명세 & 실시간 엔드포인트 테스터 */}
      <div className="bg-[#111113] border border-[#27272a] rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-[#d4ff3a] uppercase">
            BACKEND API INTEGRATION (/api/* → :8000 Proxy)
          </span>
          <span className="font-mono text-xs text-[#a1a1aa]">
            Next.js App Router + @supabase/ssr 기준
          </span>
        </div>
        <h3 className="font-mono text-lg font-bold text-white">
          프론트엔드 ↔ 백엔드 API 연결 상태 & 응답 시뮬레이터
        </h3>

        <div className="overflow-x-auto border border-[#27272a] rounded-lg">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-[#0a0a0a] text-[#a1a1aa] border-b border-[#27272a]">
              <tr>
                <th className="p-3">화면 단계</th>
                <th className="p-3">엔드포인트 요청</th>
                <th className="p-3">핵심 응답 필드</th>
                <th className="p-3">상태 / 테스트</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#27272a]">
              <tr>
                <td className="p-3">1. 로그인</td>
                <td className="p-3">
                  <code>supabase.auth.signInWithOAuth</code>
                </td>
                <td className="p-3 text-[#a1a1aa]">
                  <code>session.access_token</code> (Bearer)
                </td>
                <td className="p-3">
                  <button
                    onClick={() => handleTestApi("auth")}
                    className="px-2 py-1 rounded bg-[#18181b] border border-[#27272a] text-[#d4ff3a] cursor-pointer"
                  >
                    모달 열기
                  </button>
                </td>
              </tr>
              <tr className="bg-[#ff9f43]/5">
                <td className="p-3">2. 저장소 연결</td>
                <td className="p-3 text-[#ff9f43]">
                  <code>POST /api/scans</code> (백엔드 이슈 필요)
                </td>
                <td className="p-3 text-[#a1a1aa]">
                  <code>scan_id</code> (#21 보안엔진 트리거)
                </td>
                <td className="p-3">
                  <span className="text-[#ff9f43]">⚠ GAP (Mock 연결됨)</span>
                </td>
              </tr>
              <tr>
                <td className="p-3">3. 검사 진행</td>
                <td className="p-3">
                  <code>POST /api/scans/&#123;id&#125;/explanations</code>
                </td>
                <td className="p-3 text-[#a1a1aa]">
                  <code>queued_job_ids, poll_after_seconds</code>
                </td>
                <td className="p-3">
                  <button
                    onClick={() => handleTestApi("poll")}
                    className="px-2 py-1 rounded bg-[#18181b] border border-[#27272a] text-[#fafafa] hover:text-[#d4ff3a] cursor-pointer"
                  >
                    202 응답 보기
                  </button>
                </td>
              </tr>
              <tr>
                <td className="p-3">4·5. 목록·상세</td>
                <td className="p-3">
                  <code>GET /api/scans/&#123;id&#125;/explanations?after_id=</code>
                </td>
                <td className="p-3 text-[#a1a1aa]">
                  <code>risk.decision, guide.actions, red_verdict</code>
                </td>
                <td className="p-3">
                  <button
                    onClick={() => handleTestApi("explain")}
                    className="px-2 py-1 rounded bg-[#18181b] border border-[#27272a] text-[#fafafa] hover:text-[#d4ff3a] cursor-pointer"
                  >
                    JSON 응답 보기
                  </button>
                </td>
              </tr>
              <tr>
                <td className="p-3">완료/사고 리포트</td>
                <td className="p-3">
                  <code>POST /api/reports/plain</code> · <code>/incident-24h</code>
                </td>
                <td className="p-3 text-[#a1a1aa]">
                  <code>Report.sections</code> (#34 미검사 영역 포함)
                </td>
                <td className="p-3">
                  <button
                    onClick={() => handleTestApi("report")}
                    className="px-2 py-1 rounded bg-[#18181b] border border-[#27272a] text-[#fafafa] hover:text-[#d4ff3a] cursor-pointer"
                  >
                    JSON 응답 보기
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {apiPreviewText && (
          <pre className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] font-mono text-xs text-[#d4ff3a] overflow-x-auto">
            {apiPreviewText}
          </pre>
        )}
      </div>
    </div>
  );
};

"use client";

import React, { useState } from "react";
import { Play } from "lucide-react";

export const ArchitectureTab: React.FC = () => {
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [simLogs, setSimLogs] = useState<
    { text: string; color: "white" | "red" | "green" }[]
  >([]);
  const [isSimulating, setIsSimulating] = useState(false);

  const runSimulation = () => {
    setIsSimulating(true);
    setSimLogs([]);
    setActiveStep(null);

    const steps = [
      {
        step: 1,
        text: "[Round 1 · Blue] CWE-89 SQLi 수정안 초안 작성: 문자열 치환(replace)으로 작은따옴표만 제거하도록 지시",
        color: "white" as const,
      },
      {
        step: 2,
        text: "[Round 1 · Red ] ❌ 반려! 백슬래시(\\)나 인코딩 우회 공격에 여전히 뚫리며, 이름에 아포스트로피(O'Connor)가 들어간 정상 주문 기능이 깨집니다.",
        color: "red" as const,
      },
      {
        step: 3,
        text: "[Round 2 · Blue] Red 지적 반영 재작성: 파라미터 바인딩($1) 및 Supabase .eq('id', orderId) 메서드로 수정 지시 재작성",
        color: "white" as const,
      },
      {
        step: 4,
        text: "[Round 2 · Red ] ✓ 통과! 우회 경로 차단 확인 및 기존 주문 조회 기능 100% 유지 판정 → ④ 대응 안내(MCP)로 전달 완료",
        color: "green" as const,
      },
    ];

    steps.forEach((s, i) => {
      setTimeout(() => {
        setActiveStep(s.step);
        setSimLogs((prev) => [...prev, { text: s.text, color: s.color }]);
        if (i === steps.length - 1) {
          setIsSimulating(false);
        }
      }, (i + 1) * 600);
    });
  };

  return (
    <div className="space-y-10 animate-fadeIn">
      {/* Red-Blue 검증 루프 인터랙티브 시뮬레이터 */}
      <div className="bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden">
        <div className="chrome-bar justify-between">
          <div className="flex items-center gap-2">
            <div className="dots">
              <i />
              <i />
              <i />
            </div>
            <span className="font-mono text-xs text-[#a1a1aa] ml-2">
              GPU LLM Internal — Red Team vs Blue Team Verification Loop
            </span>
          </div>
          <button
            onClick={runSimulation}
            disabled={isSimulating}
            className="px-3 py-1 rounded bg-[#d4ff3a] text-black font-mono text-xs font-bold hover:brightness-110 transition cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>
              {isSimulating
                ? "공방 검증 시뮬레이션 중..."
                : "▶ Red–Blue 공방 루프 시뮬레이션"}
            </span>
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="max-w-3xl">
            <h3 className="font-mono text-lg font-bold text-white">
              로컬 GPU LLM 내부의 Red–Blue 자율 검증 (최대 2회 반복)
            </h3>
            <p className="text-sm text-[#a1a1aa] mt-1">
              스캐너 결과를 정규화한 뒤,{" "}
              <strong className="text-[#d4ff3a]">Blue(방어자)</strong>가 초보자
              눈높이의 수정 지시를 작성하면{" "}
              <strong className="text-[#ff5f56]">Red(공격자)</strong>가 우회
              경로와 기능 파괴 여부를 글로 공격해 검증합니다. 통과한 안전한
              가이드만 ④ 대응 안내로 내보냅니다.
            </p>
          </div>

          {/* 4단계 파이프라인 카드 */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div
              className={`tilt-card p-5 rounded-xl bg-[#0a0a0a] border space-y-2 transition-all ${
                activeStep === 1
                  ? "border-[#d4ff3a] ring-2 ring-[#d4ff3a]"
                  : "border-[#27272a]"
              }`}
            >
              <span className="font-mono text-xs text-[#a1a1aa]">STEP 01</span>
              <h4 className="font-mono text-base font-bold text-white">
                탐지 정규화 입력
              </h4>
              <p className="text-xs text-[#a1a1aa] leading-relaxed">
                Opengrep · OSV · Gitleaks 및 자체 바이브코딩 모듈 결과를 공통 JSON
                + 문맥으로 묶음
              </p>
            </div>

            <div
              className={`tilt-card p-5 rounded-xl bg-[#0a0a0a] border space-y-2 transition-all ${
                activeStep === 2
                  ? "border-[#d4ff3a] ring-2 ring-[#d4ff3a]"
                  : "border-[#d4ff3a]/50"
              }`}
            >
              <span className="font-mono text-xs text-[#d4ff3a]">
                STEP 02 · BLUE TEAM
              </span>
              <h4 className="font-mono text-base font-bold text-[#d4ff3a]">
                방어자 수정 지시 작성
              </h4>
              <p className="text-xs text-[#a1a1aa] leading-relaxed">
                쉬운 원인 설명과 환경별(Windows/macOS/Linux) 패치 명령어 및 코딩툴
                지시문 생성
              </p>
            </div>

            <div
              className={`tilt-card p-5 rounded-xl bg-[#0a0a0a] border space-y-2 transition-all ${
                activeStep === 3
                  ? "border-[#ff5f56] ring-2 ring-[#ff5f56]"
                  : "border-[#ff5f56]/50"
              }`}
            >
              <span className="font-mono text-xs text-[#ff5f56]">
                STEP 03 · RED TEAM
              </span>
              <h4 className="font-mono text-base font-bold text-[#ff5f56]">
                공격자 우회·파괴 검증
              </h4>
              <p className="text-xs text-[#a1a1aa] leading-relaxed">
                &ldquo;수정 후에도 뚫리는가? 기존 앱 기능이 깨지는가?&rdquo; 판정 후
                실패 시 지적 사항 첨부해 재작성 지시
              </p>
            </div>

            <div
              className={`tilt-card p-5 rounded-xl bg-[#0a0a0a] border space-y-2 transition-all ${
                activeStep === 4
                  ? "border-[#d4ff3a] ring-2 ring-[#d4ff3a]"
                  : "border-[#27272a]"
              }`}
            >
              <span className="font-mono text-xs text-[#d4ff3a]">
                STEP 04 · OUTPUT
              </span>
              <h4 className="font-mono text-base font-bold text-white">
                ④ 대응 안내(MCP) 전달
              </h4>
              <p className="text-xs text-[#a1a1aa] leading-relaxed">
                검증 통과 시 즉시 전달. 2회 연속 실패 시 지어내지 않고 대시보드에{" "}
                <code>수동 확인</code> 경고 표시
              </p>
            </div>
          </div>

          {/* 시뮬레이션 출력 콘솔 */}
          <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] font-mono text-xs min-h-[90px] space-y-1">
            {simLogs.length === 0 ? (
              <span className="text-[#a1a1aa]">
                $ 상단 [Red–Blue 공방 루프 시뮬레이션] 버튼을 눌러 로컬 L4 GPU
                내부의 검증 로그를 확인하세요.
              </span>
            ) : (
              simLogs.map((log, idx) => (
                <div
                  key={idx}
                  className={`py-0.5 ${
                    log.color === "red"
                      ? "text-[#ff5f56]"
                      : log.color === "green"
                      ? "text-[#d4ff3a] font-bold"
                      : "text-[#fafafa]"
                  }`}
                >
                  {log.text}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* GPU 효과 평가 설계 & 상업용 라이선스 감사 표 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* GPU 효과 평가 설계 */}
        <div className="lg:col-span-6 bg-[#111113] border border-[#27272a] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-[#d4ff3a] uppercase">
              EVALUATION DESIGN
            </span>
            <span className="font-mono text-xs text-[#a1a1aa]">
              OWASP ZAP 실제 공격 재현 기준
            </span>
          </div>
          <h3 className="font-mono text-lg font-bold text-white">
            GPU 및 Red–Blue 효과 입증 설계 (A vs B vs C vs D)
          </h3>
          <p className="text-xs sm:text-sm text-[#a1a1aa]">
            동일한 취약 데모 사이트(정답셋)를 4가지 방식으로 처리하여{" "}
            <strong className="text-white">조치 성공률(ZAP 공격 재현 실패)</strong>
            , <strong className="text-white">기능 유지율</strong>,{" "}
            <strong className="text-white">비개발자 이해도</strong>를 정량
            비교합니다.
          </p>

          <div className="space-y-3 pt-2 font-mono text-xs">
            <div className="p-3 rounded-lg bg-[#0a0a0a] border border-[#27272a]">
              <div className="flex justify-between mb-1">
                <span>
                  <b>A.</b> 스캐너 원문 결과 (가이드 없음)
                </span>
                <span className="text-[#a1a1aa]">Baseline (28%)</span>
              </div>
              <div className="w-full bg-[#18181b] h-2 rounded-full overflow-hidden">
                <div className="bg-[#71717a] h-full" style={{ width: "28%" }} />
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#0a0a0a] border border-[#27272a]">
              <div className="flex justify-between mb-1">
                <span>
                  <b>B.</b> LLM 가이드 (GPU 미사용)
                </span>
                <span className="text-[#a1a1aa]">Comparison (54%)</span>
              </div>
              <div className="w-full bg-[#18181b] h-2 rounded-full overflow-hidden">
                <div className="bg-[#ff9f43] h-full" style={{ width: "54%" }} />
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#0a0a0a] border border-[#d4ff3a]/40">
              <div className="flex justify-between mb-1">
                <span className="text-[#d4ff3a]">
                  <b>C.</b> 로컬 GPU LLM 가이드 (Blue 단독 1회)
                </span>
                <span className="text-[#d4ff3a]">GPU 효과 = C − B (78%)</span>
              </div>
              <div className="w-full bg-[#18181b] h-2 rounded-full overflow-hidden">
                <div
                  className="bg-[#d4ff3a]/80 h-full"
                  style={{ width: "78%" }}
                />
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#0a0a0a] border border-[#d4ff3a]">
              <div className="flex justify-between mb-1">
                <span className="text-[#d4ff3a] font-bold">
                  <b>D.</b> C + Red–Blue 검증 루프 (최종 제안)
                </span>
                <span className="text-[#d4ff3a] font-bold">
                  Red-Blue 효과 = D − C (96%)
                </span>
              </div>
              <div className="w-full bg-[#18181b] h-2 rounded-full overflow-hidden">
                <div className="bg-[#d4ff3a] h-full" style={{ width: "96%" }} />
              </div>
            </div>
          </div>
        </div>

        {/* 상업용 라이선스 감사 표 */}
        <div className="lg:col-span-6 bg-[#111113] border border-[#27272a] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-[#d4ff3a] uppercase">
              COMMERCIAL LICENSE AUDIT
            </span>
            <span className="font-mono text-xs text-[#a1a1aa]">
              10/30 LICENSE 전수 확인 완료
            </span>
          </div>
          <h3 className="font-mono text-lg font-bold text-white">
            보안 엔진 구성 & 라이선스 클린 정책
          </h3>
          <p className="text-xs sm:text-sm text-[#a1a1aa]">
            유료 SaaS 운영에 법적 제약이 있는 도구는 철저히 배제하고, 상업적
            이용이 안전한 엔진과{" "}
            <strong className="text-white">자체 제작 바이브코딩 특화 룰셋</strong>만
            결합했습니다.
          </p>

          <div className="overflow-x-auto border border-[#27272a] rounded-lg">
            <table className="w-full text-left font-mono text-xs">
              <thead className="bg-[#0a0a0a] text-[#a1a1aa] border-b border-[#27272a]">
                <tr>
                  <th className="p-2.5">도구 / 모듈</th>
                  <th className="p-2.5">판정</th>
                  <th className="p-2.5">라이선스</th>
                  <th className="p-2.5">용도 및 비고</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#27272a]">
                <tr>
                  <td className="p-2.5 font-bold text-white">
                    자체 룰셋 + Python 검사기
                  </td>
                  <td className="p-2.5">
                    <span className="text-[#d4ff3a]">● 사용</span>
                  </td>
                  <td className="p-2.5">자체 소유</td>
                  <td className="p-2.5 text-[#a1a1aa]">
                    Supabase RLS 누락, .env 노출 등
                  </td>
                </tr>
                <tr>
                  <td className="p-2.5 font-bold text-white">
                    Opengrep + Aikido Rules
                  </td>
                  <td className="p-2.5">
                    <span className="text-[#d4ff3a]">● 사용</span>
                  </td>
                  <td className="p-2.5">LGPL-2.1 / MIT</td>
                  <td className="p-2.5 text-[#a1a1aa]">
                    SAST 엔진 (수정 없이 실행만 호출)
                  </td>
                </tr>
                <tr>
                  <td className="p-2.5 font-bold text-white">
                    OSV-Scanner · Gitleaks
                  </td>
                  <td className="p-2.5">
                    <span className="text-[#d4ff3a]">● 사용</span>
                  </td>
                  <td className="p-2.5">Apache-2.0 / MIT</td>
                  <td className="p-2.5 text-[#a1a1aa]">
                    의존성 CVE · 비밀키 유출 탐지
                  </td>
                </tr>
                <tr>
                  <td className="p-2.5 font-bold text-white">
                    vLLM · OWASP ZAP
                  </td>
                  <td className="p-2.5">
                    <span className="text-[#d4ff3a]">● 사용</span>
                  </td>
                  <td className="p-2.5">Apache-2.0</td>
                  <td className="p-2.5 text-[#a1a1aa]">
                    GPU LLM 서빙 · 데모 공격 재현
                  </td>
                </tr>
                <tr className="bg-[#ff5f56]/5">
                  <td className="p-2.5 text-[#ff5f56]">
                    Semgrep 공식 / TruffleHog
                  </td>
                  <td className="p-2.5">
                    <span className="text-[#ff5f56]">✕ 금지</span>
                  </td>
                  <td className="p-2.5 text-[#ff5f56]">경쟁금지 / AGPL</td>
                  <td className="p-2.5 text-[#a1a1aa]">
                    SaaS 상업 이용 제한으로 배제
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

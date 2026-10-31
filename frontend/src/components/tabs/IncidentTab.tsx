"use client";

import React, { useState } from "react";
import { Copy } from "lucide-react";
import { ReportType } from "@/types/security";

interface IncidentTabProps {
  onShowToast: (msg: string) => void;
}

export const IncidentTab: React.FC<IncidentTabProps> = ({ onShowToast }) => {
  const [reportType, setReportType] = useState<ReportType>("24h");
  const [noticeTime, setNoticeTime] = useState(
    "2026-10-31 05:30경 (고객 문의로 인지)"
  );
  const [actualDamage, setActualDamage] = useState(
    "현재까지 변조 흔적 없음 (로그 추가 확인 중)"
  );
  const [contactInfo, setContactInfo] = useState(
    "약 120명 추정 / 대표 민지 (010-XXXX-XXXX, security@minji-cafe.kr)"
  );

  const parsedNotice = noticeTime.trim() || "[확인 필요 - 지어내지 않고 비워둠]";
  const parsedDamage = actualDamage.trim() || "[확인 필요 - 지어내지 않고 비워둠]";
  const parsedContact = contactInfo.trim() || "[확인 필요 - 담당자 연락처 입력 필요]";

  const draft24h = `[정보통신망법 침해사고 신고 초안]
1. 발생(인지) 일시
 - 스캐너 탐지 시각: 2026-10-31 05:42 KST
 - 사용자 이상 징후 인지 시각: ${parsedNotice}

2. 침해사고 원인 (72hours 자동 채움)
 - 브라우저 공개 번들(src/lib/supabase.ts:4) 내 관리자 키(service_role) 노출
 - 주문 조회 API(src/app/api/orders/route.ts:9) SQL Injection 취약점 (CWE-89)
 - 고객 테이블(customers) Row Level Security(RLS) 미설정

3. 피해 내용
 - 노출 가능 범위: 고객 이메일, 연락처, 주문 내역 테이블
 - 실제 유출/변조 확인 사항: ${parsedDamage}

4. 대응 현황 (72hours 조치 기록 연동)
 - 노출된 기존 service_role 키 즉시 폐기 및 서버 환경변수로 분리
 - SQL 파라미터 바인딩 적용 및 RLS 활성화 마이그레이션 완료
 - 재검사(Scan #41) 통과 확인`;

  const draft72h = `[개인정보 유출 신고서 및 정보주체 통지문 초안]
※ 24시간 침해사고 신고서의 원인과 경위를 그대로 이어받아 재사용했습니다.

1. 유출된 개인정보 항목 (추정 및 확인)
 - 회원 이메일, 전화번호, 주문 내역 (customers, orders 테이블)

2. 유출 시점과 경위 (①번 신고서에서 자동 인계)
 - 인지 시각: ${parsedNotice}
 - 경위: 프론트엔드 설정 오류로 인한 DB 관리자 키 노출 및 API 입력값 검증 누락

3. 정보주체가 피해를 최소화할 수 있는 방법
 - 동일하거나 유사한 비밀번호를 타 사이트에서 사용 중이라면 즉시 변경해 주세요.
 - 주문 내역을 사칭한 스미싱·피싱 문자나 이메일 링크 클릭에 주의해 주세요.

4. 개인정보처리자의 대응 조치 및 피해 구제 절차
 - 취약점 패치 및 기존 인증키 폐기 완료 (72hours 재검사 검증 통과)
 - 실제 피해 현황: ${parsedDamage}

5. 담당부서 및 연락처 (영향 인원 포함)
 - ${parsedContact}`;

  const currentDraft = `[데모 초안 · 실제 신고용 아님]
아래 탐지·조치·재검사 기록은 예제 데이터이며 실제 검증 결과가 아닙니다. 실제 신고 전 확인된 기록으로 교체해야 합니다.

${reportType === "24h" ? draft24h : draft72h}`;

  const handleCopyDraft = async () => {
    try {
      await navigator.clipboard.writeText(currentDraft);
      onShowToast("신고서 초안이 클립보드에 복사되었습니다.");
    } catch {
      onShowToast("복사에 실패했습니다. 클립보드 권한을 확인하거나 초안을 직접 선택해 복사해 주세요.");
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="bg-[#111113] border border-[#27272a] rounded-xl p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="font-mono text-xs text-[#ff9f43] uppercase">
              INCIDENT REPORT COPILOT (24H → 72H REUSE)
            </span>
            <h3 className="font-mono text-xl font-bold text-white mt-1">
              침해사고(24h) 및 개인정보 유출(72h) 신고서 작성 서포트
            </h3>
            <p className="text-sm text-[#a1a1aa] mt-1 max-w-3xl">
              검사 결과와 완료 리포트에서 아는 사실(원인, 파일 위치, 노출 가능
              범위, 조치 기록)은 <strong>미리 채워 넣고</strong>, 우리가 알 수
              없는 사실만 쉬운 질문으로 받아 공식 신고 창구에 붙여넣을 수 있도록
              항목별 복사를 지원합니다.
            </p>
          </div>

          {/* 신고서 종류 스위치 */}
          <div className="flex bg-[#0a0a0a] p-1 rounded-lg border border-[#27272a] font-mono text-xs">
            <button
              onClick={() => setReportType("24h")}
              className={`px-3 py-2 rounded-md font-bold cursor-pointer transition ${
                reportType === "24h"
                  ? "bg-[#d4ff3a] text-black"
                  : "text-[#a1a1aa] hover:text-white"
              }`}
            >
              ① 침해사고 신고서 · 24시간 (KISA)
            </button>
            <button
              onClick={() => setReportType("72h")}
              className={`px-3 py-2 rounded-md font-bold cursor-pointer transition ${
                reportType === "72h"
                  ? "bg-[#d4ff3a] text-black"
                  : "text-[#a1a1aa] hover:text-white"
              }`}
            >
              ② 개인정보 유출 신고서 · 72시간 (개보위)
            </button>
          </div>
        </div>

        {/* 24h -> 72h 타임라인 배너 */}
        <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] font-mono text-xs flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <span className="px-2 py-0.5 rounded bg-[#ff5f56]/20 text-[#ff5f56] border border-[#ff5f56]/40">
              0h 사고 인지
            </span>
            <span>───▶</span>
            <span className="px-2 py-0.5 rounded bg-[#d4ff3a]/20 text-[#d4ff3a] border border-[#d4ff3a]/40">
              24h 정보통신망법 침해사고 신고
            </span>
            <span>──(원인·경위 자동 재사용)──▶</span>
            <span className="px-2 py-0.5 rounded bg-[#ff9f43]/20 text-[#ff9f43] border border-[#ff9f43]/40">
              72h 개인정보보호법 유출 통지
            </span>
          </div>
          <span className="text-[#a1a1aa]">
            ※ 답이 없는 칸은 지어내지 않고 [확인 필요]로 비워 둡니다.
          </span>
        </div>

        {/* 양식 편집 & 미리보기 그리드 */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-2">
          {/* 왼쪽: 자동 채움 + 사용자 질문 */}
          <div className="lg:col-span-6 space-y-4">
            <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] space-y-3">
              <div className="font-mono text-xs text-[#d4ff3a] font-bold flex items-center justify-between">
                <span>✓ 72hours가 스캔 기록에서 미리 채운 항목</span>
                <span>AUTO-FILLED</span>
              </div>
              <div className="text-xs font-mono space-y-2 text-[#fafafa]">
                <div>
                  <span className="text-[#a1a1aa]">탐지 일시/경로:</span> 2026-10-31
                  05:42 KST (첫 전체 검사 #41)
                </div>
                <div>
                  <span className="text-[#a1a1aa]">사고 원인:</span> 브라우저
                  번들 내 Supabase <code>service_role</code> 관리자 키 노출
                  (src/lib/supabase.ts:4) 및 주문 API SQLi (CWE-89)
                </div>
                <div>
                  <span className="text-[#a1a1aa]">노출 가능 범위:</span> 고객
                  주문 테이블(이메일, 연락처, 주문내역) 전체 읽기/수정 권한
                </div>
                <div>
                  <span className="text-[#a1a1aa]">조치 현황:</span> 기존 키 즉시
                  폐기, 서버 환경변수 분리 및 RLS 정책 활성화 패치 진행
                </div>
              </div>
            </div>

            {/* 사용자 질문 입력 폼 */}
            <div className="p-4 rounded-lg bg-[#0a0a0a] border border-[#27272a] space-y-4">
              <div className="font-mono text-xs text-[#ff9f43] font-bold">
                ? 사용자에게 묻는 쉬운 질문 (모르면 비워두세요)
              </div>
              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-[#fafafa] mb-1 font-medium">
                    1. 처음 이상 징후를 알아챈 시각은 언제인가요?
                  </label>
                  <input
                    type="text"
                    value={noticeTime}
                    onChange={(e) => setNoticeTime(e.target.value)}
                    className="w-full font-mono px-3 py-2 rounded bg-[#111113] border border-[#27272a] text-white focus:outline-none focus:border-[#d4ff3a]"
                  />
                </div>
                <div>
                  <label className="block text-[#fafafa] mb-1 font-medium">
                    2. 실제로 데이터가 바뀌거나 외부로 빠져나간 흔적이 있나요?
                  </label>
                  <input
                    type="text"
                    value={actualDamage}
                    onChange={(e) => setActualDamage(e.target.value)}
                    className="w-full font-mono px-3 py-2 rounded bg-[#111113] border border-[#27272a] text-white focus:outline-none focus:border-[#d4ff3a]"
                  />
                </div>
                <div>
                  <label className="block text-[#fafafa] mb-1 font-medium">
                    3. 영향받은 회원은 몇 명이며, 연락받을 담당자 연락처는
                    무엇인가요?
                  </label>
                  <input
                    type="text"
                    value={contactInfo}
                    onChange={(e) => setContactInfo(e.target.value)}
                    className="w-full font-mono px-3 py-2 rounded bg-[#111113] border border-[#27272a] text-white focus:outline-none focus:border-[#d4ff3a]"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* 오른쪽: 실시간 신고서 초안 */}
          <div className="lg:col-span-6 bg-[#0a0a0a] border border-[#27272a] rounded-lg p-5 flex flex-col justify-between space-y-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-[#27272a] pb-3">
                <span className="font-mono text-sm font-bold text-[#d4ff3a]">
                  {reportType === "24h"
                    ? "① 정보통신망법 침해사고 신고서 초안 (24h 기한)"
                    : "② 개인정보보호법 제34조 유출 신고·통지서 초안 (72h 기한)"}
                </span>
                <button
                  onClick={handleCopyDraft}
                  className="px-3 py-1 rounded bg-[#d4ff3a] text-black font-mono text-xs font-bold hover:brightness-110 transition flex items-center gap-1.5 cursor-pointer"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>전체 초안 복사</span>
                </button>
              </div>
              <pre className="font-mono text-xs text-[#fafafa] whitespace-pre-wrap leading-relaxed overflow-x-auto min-h-[300px]">
                {currentDraft}
              </pre>
            </div>
            <div className="font-mono text-[11px] text-[#a1a1aa] border-t border-[#27272a] pt-3">
              ※ 72hours는 신고 대상 여부를 법률적으로 대리 판단하거나 대신
              제출하지 않습니다. 해킹 등 외부 침입에 의한 유출은 인원수와
              무관하게 신고 대상이 될 수 있으므로 KISA·개인정보보호위원회 공식
              창구에서 최종 확인 후 제출하세요.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

"use client";

// 웹 검사 결과를 MCP 서버(integrations/mcp-handoff)로 넘기는 칸.
// 검사가 끝나면 page.tsx 가 마지막 결과를 브라우저에 저장(saveLast)하므로, 여기서는 그 값을 읽어
// MCP 서버가 받는 JSON 파일을 만듭니다.
// - 자동 저장을 켜 두면 결과가 바뀔 때마다 같은 파일을 덮어쓰고, MCP는 호출할 때마다 최신 파일을 읽습니다.
// - 설정 복사는 최초 MCP 연결 때 한 번만 씁니다(저장소만 고정, 커밋은 파일에서 읽음).
import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Download, Copy, RefreshCw } from "lucide-react";
import { loadLast } from "@/lib/api";
import { BLOCK_LABEL, buildHandoff, clientConfig } from "@/lib/mcp";
import {
  autoSave,
  autoSaveState,
  autoSaveSupported,
  disableAutoSave,
  enableAutoSave,
  resumeAutoSave,
  type AutoSaveState,
} from "@/lib/autosave";
import type { OS } from "@/types/security";

interface Props {
  os: OS;
  onShowToast: (msg: string) => void;
}

// 다른 탭에서 저장한 결과도 반영합니다. 같은 탭의 새 검사는 부모가 다시 그릴 때 getSnapshot 으로 읽힙니다
const subscribe = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
};
// 문자열로 비교해야 값이 같을 때 다시 그리지 않습니다 (loadLast 는 매번 새 객체를 돌려줌)
const readLast = () => JSON.stringify(loadLast() ?? null);
// 서버 렌더링(정적 빌드)에는 브라우저 저장소가 없습니다
const readNothing = () => "__server__";
const noChange = () => () => {};
const unsupportedOnServer = () => false;
const clock = () => new Date().toTimeString().slice(0, 8);

const btn =
  "px-3 py-1.5 rounded-xl border font-mono text-[11px] font-bold transition flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer";

export const McpHandoff: React.FC<Props> = ({ os, onShowToast }) => {
  const raw = useSyncExternalStore(subscribe, readLast, readNothing);
  // 서버 렌더링 값(false)과 첫 화면을 맞춘 뒤 브라우저 지원 여부를 반영합니다 (하이드레이션 불일치 방지)
  const supported = useSyncExternalStore(noChange, autoSaveSupported, unsupportedOnServer);
  const handoff = useMemo(
    () =>
      raw === "__server__"
        ? { ok: false as const, why: "검사 결과를 불러오는 중..." }
        : buildHandoff(JSON.parse(raw)),
    [raw],
  );
  const text = handoff.ok ? JSON.stringify(handoff.snapshot, null, 2) : null;
  const repository = handoff.ok ? handoff.repository : null;

  const [save, setSave] = useState<{ state: AutoSaveState; at?: string }>({ state: "off" });
  const written = useRef<string | null>(null); // 같은 내용을 반복해서 쓰지 않기 위해

  // 결과가 바뀌면 자동 저장이 켜진 경우에만 같은 파일을 덮어씁니다
  useEffect(() => {
    if (!repository || !text) return;
    let cancelled = false;
    const sync = async () => {
      try {
        if (written.current === text) {
          const state = await autoSaveState(repository);
          if (!cancelled) setSave((prev) => ({ ...prev, state }));
          return;
        }
        const state = await autoSave(repository, text);
        if (cancelled) return;
        if (state === "on") written.current = text;
        setSave((prev) => ({ state, at: state === "on" ? clock() : prev.at }));
      } catch {
        if (!cancelled) setSave((prev) => ({ ...prev, state: "needs-permission" }));
      }
    };
    void sync();
    return () => {
      cancelled = true;
    };
  }, [repository, text]);

  const turnOn = async () => {
    if (!handoff.ok || !text) return;
    try {
      if (await enableAutoSave(handoff.repository, handoff.fileName, text)) {
        written.current = text;
        setSave({ state: "on", at: clock() });
        onShowToast("자동 저장을 켰습니다. 이제 검사할 때마다 같은 파일이 최신 결과로 바뀝니다.");
      }
    } catch {
      onShowToast("파일을 저장하지 못했습니다. 다른 위치를 골라 주세요.");
    }
  };

  const resume = async () => {
    if (!handoff.ok || !text) return;
    try {
      if (await resumeAutoSave(handoff.repository, text)) {
        written.current = text;
        setSave({ state: "on", at: clock() });
        onShowToast("자동 저장을 다시 시작했습니다.");
      } else {
        onShowToast("파일 접근을 허용하지 않아 자동 저장이 멈춰 있습니다.");
      }
    } catch {
      onShowToast("저장하던 파일을 찾지 못했습니다. 자동 저장을 다시 켜 주세요.");
      setSave({ state: "off" });
    }
  };

  const turnOff = async () => {
    if (!handoff.ok) return;
    await disableAutoSave(handoff.repository);
    written.current = null;
    setSave({ state: "off" });
    onShowToast("자동 저장을 껐습니다. 이미 저장된 파일은 그대로 남아 있습니다.");
  };

  const download = () => {
    if (!handoff.ok || !text) return;
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = handoff.fileName;
    a.click();
    URL.revokeObjectURL(url);
    onShowToast(
      `MCP용 결과 파일을 저장했습니다: ${handoff.fileName} (같은 이름으로 덮어써야 MCP가 최신 결과를 읽습니다)`,
    );
  };

  const copyConfig = async () => {
    if (!handoff.ok) return;
    try {
      await navigator.clipboard.writeText(clientConfig(handoff, os));
      onShowToast("MCP 설정을 복사했습니다. 경로의 <사용자>와 설치 위치를 바꿔 한 번만 붙여 넣으세요.");
    } catch {
      onShowToast("복사에 실패했습니다. 클립보드 권한을 확인해 주세요.");
    }
  };

  const status = !handoff.ok
    ? null
    : !supported
      ? "이 브라우저는 자동 저장을 지원하지 않습니다(크롬·엣지 지원). 검사 후 '내려받기'로 같은 파일 이름에 저장하세요."
      : save.state === "on"
        ? `자동 저장 중 · ${handoff.fileName}${save.at ? ` · ${save.at} 저장됨` : ""}`
        : save.state === "needs-permission"
          ? "자동 저장이 멈춰 있습니다. 브라우저를 다시 열면 파일 접근을 한 번 다시 허용해야 합니다."
          : "자동 저장이 꺼져 있습니다. 켜 두면 검사할 때마다 MCP가 읽는 파일이 최신 결과로 바뀝니다.";

  return (
    <div
      className="pt-3 mt-3 border-t border-sky-100 space-y-2"
      data-testid="mcp-handoff"
    >
      <div className="font-mono text-[11px] text-slate-600">
        {handoff.ok ? (
          <>
            검사 대상 <code className="text-[#0284C7] font-bold">{handoff.repository}</code>@
            <code>{handoff.revision.slice(0, 7)}</code> · 전달 가능{" "}
            <b className="text-[#0D9488]">{handoff.ready}건</b>
            {handoff.blocked.length > 0 && (
              <>
                {" "}
                · 차단{" "}
                {handoff.blocked
                  .map((b) => `${BLOCK_LABEL[b.reason]} ${b.count}`)
                  .join(", ")}
              </>
            )}
          </>
        ) : (
          handoff.why
        )}
      </div>
      {status && (
        <div
          data-testid="mcp-autosave-status"
          className={`font-mono text-[11px] ${
            save.state === "on"
              ? "text-[#0D9488] font-bold"
              : "text-slate-500"
          }`}
        >
          {status}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {supported && save.state === "off" && (
          <button
            onClick={turnOn}
            disabled={!handoff.ok}
            className={`${btn} border-[#0284C7] bg-[#0284C7] text-white hover:bg-[#0D9488] hover:border-[#0D9488]`}
          >
            <RefreshCw className="w-3.5 h-3.5" /> 자동 저장 켜기
          </button>
        )}
        {supported && save.state === "needs-permission" && (
          <button
            onClick={resume}
            disabled={!handoff.ok}
            className={`${btn} border-[#0284C7] bg-[#0284C7] text-white hover:bg-[#0D9488]`}
          >
            <RefreshCw className="w-3.5 h-3.5" /> 자동 저장 다시 허용
          </button>
        )}
        {supported && save.state === "on" && (
          <button
            onClick={turnOff}
            disabled={!handoff.ok}
            className={`${btn} border-slate-200 text-slate-600 hover:border-[#0D9488]`}
          >
            자동 저장 끄기
          </button>
        )}
        <button
          onClick={download}
          disabled={!handoff.ok}
          className={`${btn} border-[#0D9488] text-[#0D9488] hover:bg-teal-50`}
        >
          <Download className="w-3.5 h-3.5" /> MCP용 결과 내려받기
        </button>
        <button
          onClick={copyConfig}
          disabled={!handoff.ok}
          className={`${btn} border-sky-200 text-[#0284C7] hover:bg-sky-50`}
        >
          <Copy className="w-3.5 h-3.5" /> MCP 설정 복사 (최초 1회)
        </button>
      </div>
    </div>
  );
};

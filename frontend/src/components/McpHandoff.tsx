"use client";

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

const subscribe = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
};
const readLast = () => JSON.stringify(loadLast() ?? null);
const readNothing = () => "__server__";
const noChange = () => () => {};
const unsupportedOnServer = () => false;
const clock = () => new Date().toTimeString().slice(0, 8);

const btn =
  "px-3 py-1.5 rounded-[14px_4px_14px_4px] border font-mono text-[11.5px] font-bold transition flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer";

export const McpHandoff: React.FC<Props> = ({ os, onShowToast }) => {
  const raw = useSyncExternalStore(subscribe, readLast, readNothing);
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
  const written = useRef<string | null>(null);

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
      className="pt-4 mt-4 border-t border-[var(--ink-line)] space-y-2.5"
      data-testid="mcp-handoff"
    >
      <div className="font-mono text-xs text-[var(--ink-jung)]">
        {handoff.ok ? (
          <>
            검사 대상 <code>{handoff.repository}</code>@
            <code>{handoff.revision.slice(0, 7)}</code> · 전달 가능{" "}
            <b className="text-[var(--jade-deep)]">{handoff.ready}건</b>
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
          className={`font-mono text-[11.5px] ${
            save.state === "on"
              ? "text-[var(--jade-deep)] font-bold"
              : "text-[var(--ink-jung)]"
          }`}
        >
          {status}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {supported && save.state === "off" && (
          <button
            onClick={turnOn}
            disabled={!handoff.ok}
            className={`${btn} border-[var(--ink-nong)] bg-[var(--ink-nong)] text-[var(--paper-bg)] hover:bg-[var(--jade-deep)] hover:border-[var(--jade-deep)]`}
          >
            <RefreshCw className="w-3.5 h-3.5" /> 자동 저장 켜기
          </button>
        )}
        {supported && save.state === "needs-permission" && (
          <button
            onClick={resume}
            disabled={!handoff.ok}
            className={`${btn} border-[var(--ink-nong)] bg-[var(--ink-nong)] text-[var(--paper-bg)] hover:bg-[var(--jade-deep)]`}
          >
            <RefreshCw className="w-3.5 h-3.5" /> 자동 저장 다시 허용
          </button>
        )}
        {supported && save.state === "on" && (
          <button
            onClick={turnOff}
            disabled={!handoff.ok}
            className={`${btn} border-[var(--ink-line)] text-[var(--ink-jung)] hover:border-[var(--jade-deep)]`}
          >
            자동 저장 끄기
          </button>
        )}
        <button
          onClick={download}
          disabled={!handoff.ok}
          className={`${btn} border-[var(--jade-deep)] text-[var(--jade-deep)] hover:bg-[var(--jade-soft)]`}
        >
          <Download className="w-3.5 h-3.5" /> MCP용 결과 내려받기
        </button>
        <button
          onClick={copyConfig}
          disabled={!handoff.ok}
          className={`${btn} border-[var(--ink-line)] text-[var(--ink-nong)] hover:border-[var(--ink-nong)]`}
        >
          <Copy className="w-3.5 h-3.5" /> MCP 설정 복사 (최초 1회)
        </button>
      </div>
      <p className="font-mono text-[11px] text-[var(--ink-dam)] leading-relaxed">
        처음 한 번 자동 저장을 켜고 설정을 AI 코딩툴(Cursor·Claude Code)의 MCP 설정에
        붙여 넣으면, 그 뒤로는 검사만 해도 에이전트가{" "}
        <code>list_findings</code>로 최신 목록을 보고 <code>get_fix_prompt</code>
        로 Red 검증을 통과한 수정 지시만 받습니다.
      </p>
    </div>
  );
};

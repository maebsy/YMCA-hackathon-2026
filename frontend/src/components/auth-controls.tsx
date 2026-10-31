"use client";

import { useEffect, useState } from "react";
import { getGitHubUsername, isAuthEnabled, signInWithGitHub, signOut, subscribeAuth, type User } from "@/lib/auth";

export default function AuthControls() {
  const [user, setUser] = useState<User | null>(null);
  const [busy, setBusy] = useState<"login" | "logout" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const enabled = isAuthEnabled();

  useEffect(() => {
    if (!enabled) return;
    return subscribeAuth((nextUser) => { setUser(nextUser); });
  }, [enabled]);

  async function handleAuth() {
    if (busy) return;
    const action = user ? "logout" : "login";
    setError(null);
    setBusy(action);
    try {
      if (action === "logout") await signOut();
      else await signInWithGitHub();
    } catch {
      setError(action === "logout" ? "로그아웃하지 못했습니다. 다시 시도해 주세요." : "GitHub 로그인에 연결하지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setBusy(null);
    }
  }

  if (!enabled) return null;

  const username = user ? getGitHubUsername(user) : "";
  const userLabel = user ? username ? `@${username}` : "GitHub 로그인됨" : null;
  return <div className="auth-controls">
    <div className="auth-actions">
      {userLabel && <><span className="auth-username" title={userLabel}>{userLabel}</span><span aria-hidden="true">·</span></>}
      <button type="button" className="auth-button" onClick={handleAuth} disabled={busy !== null}>
        {busy === "login" ? "로그인 중…" : busy === "logout" ? "로그아웃 중…" : user ? "로그아웃" : "GitHub로 로그인"}
      </button>
    </div>
    {busy && <span className="sr-only" role="status">{busy === "login" ? "GitHub 로그인에 연결하고 있습니다." : "로그아웃하고 있습니다."}</span>}
    {error && <p className="auth-error" role="alert">{error}</p>}
  </div>;
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { Moon, ShieldCheck, Sun } from "lucide-react";
import { useRepository } from "@/components/repository-provider";
import { REPOSITORY_PROGRESS_PATH, REPOSITORY_RESULT_PATH } from "@/lib/repository-routes";


export function Brand() {
  return <span className="brand"><ShieldCheck size={28} strokeWidth={1.5}/><span>72<span className="brand-hours">hours</span><span className="accent">.</span></span></span>;
}

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // The provider starts empty on both server and client, then restores in an effect.
  const { isScanning, result } = useRepository();
  const repositoryHref = isScanning ? REPOSITORY_PROGRESS_PATH : result ? REPOSITORY_RESULT_PATH : "/";
  const repositoryLabel = isScanning ? "검사 진행" : result ? "검사 결과" : "GitHub 실제 검사";
  useEffect(() => {
    try { document.documentElement.dataset.theme = localStorage.getItem("72hours-theme") === "light" ? "light" : "dark"; } catch { /* optional storage */ }
  }, []);
  useEffect(() => {
    const frame = requestAnimationFrame(() => document.getElementById("main")?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [pathname]);
  function toggleTheme() {
    const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("72hours-theme", theme); } catch { /* theme still works */ }
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main">본문으로 바로가기</a>
    <header className="site-header container">
      <Link href="/" aria-label="72hours 홈"><Brand/></Link>
      <span className="header-note">만드는 사람 곁의 보안 가이드</span>
      <nav className="header-actions" aria-label="보조 메뉴">
        <Link href={repositoryHref} aria-current={pathname === repositoryHref ? "page" : undefined}>{repositoryLabel}</Link>
        <Link href="/incident" aria-current={pathname === "/incident" ? "page" : undefined}>사고 신고</Link>
        <Link href="/help" aria-current={pathname === "/help" ? "page" : undefined}>도움말</Link>
        <button className="icon-button theme-toggle" onClick={toggleTheme} aria-label="밝은 테마와 어두운 테마 전환"><Sun className="sun-icon" size={18}/><Moon className="moon-icon" size={18}/></button>
      </nav>
    </header>
    {children}
    <footer className="site-footer"><div className="container footer-inner"><p>© 2026 72hours <span>·</span> 작은 서비스의 더 안전한 다음 단계.</p><Link href="/help">사용 방법과 검사 범위</Link></div></footer>
  </div>;
}

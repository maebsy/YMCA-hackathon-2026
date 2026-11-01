"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ArrowUpRight, BookOpen, Code2, LifeBuoy, Moon, ShieldCheck, Sun } from "lucide-react";
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
    <footer className="site-footer corporate-footer">
      <div className="container footer-grid">
        <div className="footer-brand-block">
          <Link className="footer-brand-link" href="/" aria-label="72hours 홈으로"><Brand/></Link>
          <p className="footer-tagline">만드는 사람 곁의 보안 가이드.</p>
          <p className="footer-description">발견부터 수정과 재검사까지,<br/>작은 서비스의 더 안전한 다음 단계를 함께합니다.</p>
          <span className="footer-signature"><ShieldCheck size={15} aria-hidden="true"/>SECURITY FOR BUILDERS</span>
        </div>
        <nav className="footer-link-group" aria-label="푸터 서비스">
          <h2><ShieldCheck size={16} aria-hidden="true"/>서비스</h2>
          <Link href={repositoryHref}>{repositoryLabel}<ArrowUpRight size={14} aria-hidden="true"/></Link>
          <Link href="/incident">사고 신고 준비<ArrowUpRight size={14} aria-hidden="true"/></Link>
          <Link href="/verify">데모 실검증<ArrowUpRight size={14} aria-hidden="true"/></Link>
        </nav>
        <nav className="footer-link-group" aria-label="푸터 리소스">
          <h2><BookOpen size={16} aria-hidden="true"/>리소스</h2>
          <Link href="/help"><span><LifeBuoy size={15} aria-hidden="true"/>사용 방법과 검사 범위</span><ArrowUpRight size={14} aria-hidden="true"/></Link>
          <a href="https://github.com/maebsy/YMCA-hackathon-2026" target="_blank" rel="noopener noreferrer" aria-label="GitHub 프로젝트 (새 탭)"><span><Code2 size={15} aria-hidden="true"/>GitHub 프로젝트</span><ArrowUpRight size={14} aria-hidden="true"/></a>
        </nav>
      </div>
      <div className="container footer-bottom"><p>© 2026 72hours. All rights reserved.</p><p>만드는 사람을 위한 더 안전한 웹.</p></div>
    </footer>
  </div>;
}

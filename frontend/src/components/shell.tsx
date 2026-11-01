"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Menu, Moon, ShieldAlert, ShieldCheck, Sun, X } from "lucide-react";
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
  const repositoryLabel = isScanning ? "진행 중" : result ? "결과" : "점검";
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const homeLink = useRef<HTMLAnchorElement>(null);
  const menuPanel = useRef<HTMLElement>(null);
  const menuOpenRef = useRef(false);
  const closeMenu = useCallback(() => {
    setMenuOpen(false);
    if (menuOpenRef.current) {
      const target = menuButton.current?.getClientRects().length ? menuButton.current : homeLink.current;
      target?.focus({ preventScroll: true });
    }
    menuOpenRef.current = false;
  }, []);
  useEffect(() => {
    try { document.documentElement.dataset.theme = localStorage.getItem("72hours-theme") === "light" ? "light" : "dark"; } catch { /* optional storage */ }
  }, []);
  useEffect(() => {
    const closeForRoute = menuOpenRef.current;
    const frame = requestAnimationFrame(() => {
      if (closeForRoute) closeMenu();
      else document.getElementById("main")?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [pathname, closeMenu]);
  useEffect(() => {
    if (!menuOpen) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && !menuPanel.current?.contains(target) && !menuButton.current?.contains(target)) {
        event.preventDefault();
        closeMenu();
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeMenu(); }
    };
    const desktop = window.matchMedia("(min-width: 769px)");
    const resize = () => { if (desktop.matches) closeMenu(); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    desktop.addEventListener("change", resize);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      desktop.removeEventListener("change", resize);
    };
  }, [menuOpen, closeMenu]);
  function toggleTheme() {
    const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("72hours-theme", theme); } catch { /* theme still works */ }
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main">본문으로 바로가기</a>
    <header className="site-header container">
      <Link ref={homeLink} href="/" aria-label="72hours 홈"><Brand/></Link>
      <span className="header-note">찾고, 고치고, 확인까지</span>
      <nav className="header-actions" aria-label="보조 메뉴">
        <Link href={repositoryHref} aria-current={pathname === repositoryHref ? "page" : undefined}>{repositoryLabel}</Link>
        {/* 핵심 기능 세 가지는 따로 강조합니다 (최종 멘토링: 실검증·MCP·사고 신고가 카테고리로 잘 보여야 함) */}
        <Link className="nav-core" href="/verify" aria-current={pathname === "/verify" ? "page" : undefined}>실제검증</Link>
        <Link className="nav-core" href="/mcp-guide" aria-current={pathname === "/mcp-guide" ? "page" : undefined}>MCP</Link>
        <Link className="header-incident-link" href="/incident" aria-current={pathname === "/incident" ? "page" : undefined}><ShieldAlert size={16} aria-hidden="true"/>사고 신고 72h</Link>
        <Link href="/help" aria-current={pathname === "/help" ? "page" : undefined}>사용법</Link>
        <button className="icon-button theme-toggle" onClick={toggleTheme} aria-label="밝은 테마와 어두운 테마 전환"><Sun className="sun-icon" size={18}/><Moon className="moon-icon" size={18}/></button>
      </nav>
      <Link className="header-incident-link mobile-incident" href="/incident" aria-current={pathname === "/incident" ? "page" : undefined}><ShieldAlert size={16} aria-hidden="true"/>사고 신고 72h</Link>
      <button ref={menuButton} className="icon-button menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="header-menu" aria-label={menuOpen ? "메뉴 닫기" : "메뉴 열기"} onClick={() => {
        if (menuOpen) closeMenu();
        else { menuOpenRef.current = true; setMenuOpen(true); }
      }}>{menuOpen ? <X size={22} aria-hidden="true"/> : <Menu size={22} aria-hidden="true"/>}</button>
      <nav ref={menuPanel} id="header-menu" className="header-menu" aria-label="전체 메뉴" hidden={!menuOpen}>
        <Link href={repositoryHref} onClick={closeMenu} aria-current={pathname === repositoryHref ? "page" : undefined}>{isScanning ? "검사 진행" : result ? "검사 결과" : "GitHub 실제 검사"}</Link>
        <Link href="/verify" onClick={closeMenu} aria-current={pathname === "/verify" ? "page" : undefined}>실제검증</Link>
        <Link href="/mcp-guide" onClick={closeMenu} aria-current={pathname === "/mcp-guide" ? "page" : undefined}>MCP</Link>
        <Link href="/incident" onClick={closeMenu} aria-current={pathname === "/incident" ? "page" : undefined}>사고 신고 72h</Link>
        <Link href="/help" onClick={closeMenu} aria-current={pathname === "/help" ? "page" : undefined}>도움말</Link>
        <button className="menu-theme" type="button" onClick={toggleTheme}><Sun className="sun-icon" size={18} aria-hidden="true"/><Moon className="moon-icon" size={18} aria-hidden="true"/>테마 전환</button>
      </nav>
    </header>
    {children}
    <footer className="site-footer"><div className="container footer-inner"><p>© 2026 72hours <span>·</span> 사고 나기 전에 찾고, 나면 72시간 안에.</p><Link href="/help">사용법과 점검 범위</Link></div></footer>
  </div>;
}

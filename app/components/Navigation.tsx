"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "오늘의 시그널", icon: "⌁" },
  { href: "/portfolio", label: "내 포트폴리오", icon: "◫" },
  { href: "/stock/005930", label: "종목 리서치", icon: "⌕" },
  { href: "/news", label: "뉴스 분석실", icon: "N" },
  { href: "/news/archive", label: "기사 아카이브", icon: "▤" },
  { href: "/news/providers", label: "AI 공급자", icon: "◈" },
];

function activeHref(pathname: string) {
  // 더 깊은 경로가 있으면 그쪽만 활성화한다. (/news 와 /news/archive)
  return links
    .filter((link) => (link.href === "/" ? pathname === "/" : pathname === link.href || pathname.startsWith(`${link.href}/`)))
    .sort((left, right) => right.href.length - left.href.length)[0]?.href;
}

export function Navigation() {
  const pathname = usePathname();
  const current = activeHref(pathname);

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="Signalist 홈">
        <span className="brand-mark">S</span>
        <span>signalist</span>
      </Link>
      <nav className="side-nav" aria-label="주 메뉴">
        <span className="nav-eyebrow">WORKSPACE</span>
        {links.map((link) => {
          const active = link.href === current;
          return (
            <Link key={link.href} href={link.href} className={active ? "nav-link active" : "nav-link"}>
              <span className="nav-icon">{link.icon}</span>
              {link.label}
            </Link>
          );
        })}
      </nav>
      <div className="side-insight">
        <span className="pulse-dot" />
        <div>
          <strong>데이터 정상</strong>
          <p>6개 소스 · 2분 전</p>
        </div>
      </div>
      <div className="side-footer">
        <span className="avatar">W</span>
        <div><strong>개인 워크스페이스</strong><small>균형형 · 1~4주</small></div>
      </div>
    </aside>
  );
}

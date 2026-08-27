import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  // OG·트위터 이미지의 절대 URL을 만들 기준. 배포 도메인을 환경변수로 넣는다.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Signalist | AI 주식 리서치", template: "%s | Signalist" },
  description: "재무, 수급, 가격, 뉴스와 거시경제를 함께 해석하는 AI 투자 리서치 워크스페이스",
  openGraph: {
    title: "Signalist | AI 주식 리서치",
    description: "PER·PBR부터 VIX, 환율, 채권과 뉴스까지 연결하는 근거 중심 투자 리서치",
    type: "website",
    locale: "ko_KR",
    images: [{ url: "/og.png", width: 1729, height: 910, alt: "Signalist AI 주식 리서치" }],
  },
  twitter: { card: "summary_large_image", images: ["/og.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

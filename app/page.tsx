import type { Metadata } from "next";
import { Dashboard } from "./Dashboard";

export const metadata: Metadata = {
  title: "Signalist | AI 주식 리서치",
  description: "시장 데이터, 기업가치, 뉴스와 거시환경을 연결하는 개인 투자 리서치 도구",
};

export default function Home() {
  return <Dashboard />;
}

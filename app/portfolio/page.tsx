import type { Metadata } from "next";
import { PortfolioView } from "./PortfolioView";
export const metadata: Metadata = { title: "내 포트폴리오" };
export default function PortfolioPage() { return <PortfolioView />; }

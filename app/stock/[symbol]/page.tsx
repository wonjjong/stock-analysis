import type { Metadata } from "next";
import { getStock } from "../../data";
import { StockDetail } from "./StockDetail";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }): Promise<Metadata> {
  const { symbol } = await params;
  return { title: `${getStock(symbol).name} AI 분석` };
}

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <StockDetail stock={getStock(symbol)} />;
}

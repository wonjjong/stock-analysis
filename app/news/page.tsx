import type { Metadata } from "next";
import { NewsLab } from "./NewsLab";

export const metadata: Metadata = { title: "뉴스 분석실" };
export default function NewsPage() { return <NewsLab />; }

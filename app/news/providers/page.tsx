import type { Metadata } from "next";
import { NewsProviders } from "./NewsProviders";

export const metadata: Metadata = { title: "AI 공급자 설정" };
export default function NewsProvidersPage() { return <NewsProviders />; }

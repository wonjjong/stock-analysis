import type { Metadata } from "next";
import { NewsSources } from "./NewsSources";

export const metadata: Metadata = { title: "뉴스 자동 수집" };
export default function NewsSourcesPage() { return <NewsSources />; }

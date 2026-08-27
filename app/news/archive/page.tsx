import type { Metadata } from "next";
import { NewsArchive } from "./NewsArchive";

export const metadata: Metadata = { title: "뉴스 기사 아카이브" };
export default function NewsArchivePage() { return <NewsArchive />; }

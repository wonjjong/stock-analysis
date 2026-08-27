import { getD1 } from "../../../../../../db";
import { crawlSource } from "../../../../../lib/news-crawler";

type Context = { params: Promise<{ id: string }> };

export async function POST(_request: Request, { params }: Context) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) return Response.json({ error: "잘못된 소스 ID입니다." }, { status: 400 });
  try {
    return Response.json(await crawlSource(getD1(), id));
  } catch (reason) {
    return Response.json({ error: reason instanceof Error ? reason.message : "수집에 실패했습니다." }, { status: 502 });
  }
}

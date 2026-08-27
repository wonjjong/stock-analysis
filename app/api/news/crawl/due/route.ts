import { getD1 } from "../../../../../db";
import { crawlDueSources } from "../../../../lib/news-crawler";

export async function POST() {
  const results = await crawlDueSources(getD1());
  return Response.json({ processed: results.length, results });
}

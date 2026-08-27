from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    """DB 연결과 이식 대상 테이블 존재를 함께 확인한다."""
    tables: dict[str, int | str] = {}
    try:
        with connection.cursor() as cursor:
            for name in ("news_sources", "news_articles", "news_insights", "news_article_symbols"):
                cursor.execute(f"SELECT count(*) FROM {name}")
                tables[name] = cursor.fetchone()[0]
        status = "ok"
    except Exception as reason:
        status = "error"
        tables = {"error": str(reason)}
    return JsonResponse({"status": status, "tables": tables})

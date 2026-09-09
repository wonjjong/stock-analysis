from django.contrib import admin
from django.urls import path

from news import views
from research import views as research_views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("news/sources", views.sources, name="sources"),
    path("news/sources/create", views.source_create, name="source_create"),
    path("news/sources/<int:source_id>/<str:action>", views.source_action, name="source_action"),
    path("news/archive", views.archive, name="archive"),
    path("news/insights/run", views.run_insights, name="run_insights"),
    path("news/providers", views.providers, name="providers"),
    path("news/providers/create", views.provider_create, name="provider_create"),
    path(
        "news/providers/<int:provider_id>/<str:action>",
        views.provider_action,
        name="provider_action",
    ),
    path("news/lab", views.lab, name="lab"),
    path("research/lab", research_views.stock_lab, name="stock_lab"),
    path("research/lab/preview", research_views.stock_lab_preview, name="stock_lab_preview"),
    path("api/research/stocks/search", research_views.stock_search, name="stock_search"),
    path("api/research/valuation", research_views.valuation_scenario, name="valuation_scenario"),
    path("research/rank", research_views.rank_stocks, name="rank_stocks"),
    path("research/api-test", research_views.api_test, name="api_test"),
    path(
        "api/research/stocks/<str:symbol>/analyze",
        research_views.analyze_stock,
        name="analyze_stock",
    ),
    path("admin/", admin.site.urls),
    path("healthz", views.healthz, name="healthz"),
]

from django.contrib import admin
from django.urls import path

from news import views

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
    path("admin/", admin.site.urls),
    path("healthz", views.healthz, name="healthz"),
]

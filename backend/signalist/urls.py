from django.contrib import admin
from django.urls import path

from news import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", views.healthz, name="healthz"),
]

from django.urls import path

from news import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
]

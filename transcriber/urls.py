from django.urls import path

from . import views

app_name = "transcriber"

urlpatterns = [
    path("", views.LiveView.as_view(), name="live"),
    path("history/", views.TranscriptionListView.as_view(), name="list"),
    path("history/new/", views.TranscriptionCreateView.as_view(), name="create"),
    path("history/<int:pk>/edit/", views.TranscriptionUpdateView.as_view(), name="update"),
    path("history/<int:pk>/delete/", views.TranscriptionDeleteView.as_view(), name="delete"),
]

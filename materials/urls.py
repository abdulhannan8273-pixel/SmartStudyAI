
from django.urls import path
from . import views

urlpatterns = [
    path("upload/", views.upload_material, name="upload_material"),
    path(
        "notes/<int:material_id>/",
        views.create_notes,
        name="create_notes",
    ),
    path(
        "topic/",
        views.study_topic,
        name="study_topic",
    ),
    path(
    "notes/<int:material_id>/download/",
    views.download_notes_pdf,
    name="download_notes_pdf",
),
]

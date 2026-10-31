from django.urls import path
from . import views

urlpatterns = [
    path("upload/", views.upload_material, name="upload_material"),
    path("notes/<int:material_id>/", views.create_notes, name="create_notes"),
    path(
        "notes/<int:material_id>/download/",
        views.download_notes_pdf,
        name="download_notes_pdf",
    ),
    path("topic/", views.study_topic, name="study_topic"),
    path("saved/", views.saved_notes_list, name="saved_notes_list"),
    path("saved/<int:notes_id>/", views.saved_notes_detail, name="saved_notes_detail"),
    path(
        "saved/<int:notes_id>/delete/",
        views.delete_saved_notes,
        name="delete_saved_notes",
    ),
    path(
        "material/<int:material_id>/delete/",
        views.delete_material,
        name="delete_material",
    ),

        path("quiz/", views.quiz_home, name="quiz_home"),
    path("quiz/scores/", views.quiz_scores, name="quiz_scores"),
    path("quiz/<int:notes_id>/", views.quiz_take, name="quiz_take"),
]
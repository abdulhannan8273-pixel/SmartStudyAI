
from django.db import models


class StudyMaterial(models.Model):
    title = models.CharField(max_length=200)
    pdf_file = models.FileField(upload_to="study_pdfs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ExtractedMaterialText(models.Model):
    material = models.OneToOneField(
        StudyMaterial,
        on_delete=models.CASCADE,
        related_name="extracted_text",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Extracted text for {self.material.title}"



class SavedStudyNotes(models.Model):
    topic = models.CharField(max_length=300)
    language = models.CharField(max_length=20, default="English")
    education_level = models.CharField(max_length=100, default="College / University")
    purpose = models.CharField(max_length=100, default="All")

    # Store the generated chapter as JSON text.
    notes_json = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.topic} - {self.created_at:%Y-%m-%d}"

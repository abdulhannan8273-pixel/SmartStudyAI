import re
import pymupdf
import os
from dotenv import load_dotenv

load_dotenv()
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import (
    StudyMaterial, ExtractedMaterialText, SavedStudyNotes, Quiz, QuizAttempt,
)
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from xml.sax.saxutils import escape


def upload_material(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        uploaded_file = request.FILES.get("pdf_file")

        if not title:
            messages.error(request, "Please enter a title.")

        elif not uploaded_file:
            messages.error(request, "Please select a PDF file.")

        elif not uploaded_file.name.lower().endswith(".pdf"):
            messages.error(request, "Only PDF files are allowed.")

        elif uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "PDF size must be 10 MB or less.")

        else:
            try:
                pdf_bytes = uploaded_file.read()
                uploaded_file.seek(0)

                with pymupdf.open(
                    stream=pdf_bytes,
                    filetype="pdf",
                ) as pdf:
                    if pdf.page_count == 0:
                        raise ValueError("The PDF has no pages.")

                    page_count = pdf.page_count
                    extracted_text = "\n".join(
                        page.get_text("text") for page in pdf
                    ).strip()

                if not extracted_text:
                    messages.error(
                        request,
                        "No readable text found. Scanned PDFs need OCR.",
                    )
                else:
                    material = StudyMaterial.objects.create(
                        title=title,
                        pdf_file=uploaded_file,
                    )

                    ExtractedMaterialText.objects.create(
                        material=material,
                        content=extracted_text[:1_000_000],
                    )

                    messages.success(
                        request,
                        f"PDF uploaded and text saved successfully! "
                        f"Pages: {page_count}. "
                        f"Extracted characters: "
                        f"{min(len(extracted_text), 1_000_000)}",
                    )
                    return redirect("upload_material")

            except (pymupdf.FileDataError, ValueError):
                messages.error(
                    request,
                    "This PDF is invalid, damaged, or cannot be read.",
                )

            except Exception as error:
                print("PDF upload failed:", type(error).__name__)
                messages.error(
                    request,
                    "The PDF could not be saved. Please try again.",
                )

    materials = StudyMaterial.objects.order_by("-uploaded_at")

    return render(
        request,
        "materials/upload.html",
        {
            "materials": materials,
            "extracted_text": "",
        },
    )



def call_groq_with_retry(client, **kwargs):
    import time
    from openai import RateLimitError

    for attempt in range(4):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == 3:
                raise
            time.sleep(20 * (attempt + 1))





def generate_study_notes(text, language="English", education_level="Not specified", purpose="All"):
    import json
    import os

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return [{
            "heading": "Configuration Error",
            "points": ["GROQ_API_KEY is missing from the .env file."]
        }]

    if not text or not text.strip():
        return [{
            "heading": "No Readable Text",
            "points": ["No readable study text was provided."]
        }]

    text = text[:1_000_000]
    chunk_size = 12_000
    chunks = [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
    ]

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=90.0,
        max_retries=1,
    )

    all_notes = []
    MAX_PARTS = 3
    total_parts = len(chunks)
    skipped_parts = max(0, total_parts - MAX_PARTS)
    chunks = chunks[:MAX_PARTS]
    failed_chunks = []

    for index, chunk in enumerate(chunks, start=1):
        prompt = f"""
Act as an expert teacher and textbook author.

Learner preferences:
- Language: {language}
- Education level/course: {education_level}
- Learning purpose: {purpose}

Create comprehensive, full-chapter-style study notes from the supplied source.
Do not write only a short summary or a few bullet points.

Include, where supported by the source:
1. Chapter overview and learning objectives.
2. Important definitions and terminology.
3. Detailed, step-by-step explanations of concepts.
4. Examples explained clearly.
5. Real-world applications.
6. Types, features, advantages and disadvantages when relevant.
7. Diagrams described in a simple text format when useful.
8. Exam questions with model answers: short and long answers.
9. Important revision points and a chapter summary.

Rules:
- Adapt the explanation to the learner's education level.
- Explain difficult terms in simple language.
- Preserve important technical terms.
- Stay faithful to the supplied source. Do not invent facts or pretend
  that unsupported details appeared in it.
- If useful information is missing from the source, state that clearly.
- Avoid unnecessary repetition.
- Make each section detailed and useful for learning.
- Write in the requested language.
- Return valid JSON only, using this structure:
{{
  "sections": [
    {{
      "heading": "Section heading",
      "points": [
        "Detailed explanation...",
        "Example..."
      ]
    }}
  ]
}}

This is part {index} of {len(chunks)}.
Focus on this part of the source, while preserving its context.

SOURCE TEXT:
{chunk}
"""

        try:
            response = call_groq_with_retry(
                client,
                model="openai/gpt-oss-20b",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a careful, thorough teacher. "
                            "Produce detailed, accurate study notes. "
                            "Return valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=6000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty AI response.")

            result = json.loads(content)
            if isinstance(result, list):
                sections = result
            elif isinstance(result, dict):
                sections = result.get("sections", [])
            else:
                raise ValueError("Unexpected AI response format.")

            if not isinstance(sections, list):
                raise ValueError("Invalid sections in AI response.")

            for section in sections:
                if not isinstance(section, dict):
                    continue

                heading = section.get("heading", "Study Notes")
                points = section.get("points", [])

                if isinstance(heading, str) and isinstance(points, list):
                    clean_points = [
                        point.strip()
                        for point in points
                        if isinstance(point, str) and point.strip()
                    ]

                    if clean_points:
                        all_notes.append({
                            "heading": heading,
                            "points": clean_points,
                        })

            print(f"Processed part {index}/{len(chunks)}")

        except Exception as error:
            print(
                f"Notes generation failed for part {index}:",
                type(error).__name__,
            )
            failed_chunks.append(index)

    if failed_chunks:
        all_notes.append({
            "heading": "Processing Notice",
            "points": [
                f"These source parts could not be processed: {failed_chunks}.",
                "The notes may be incomplete. You can retry later."
            ],
        })

    if not all_notes:
        return [{
            "heading": "Notes Could Not Be Generated",
            "points": [
                "No notes were generated successfully.",
                "Check the server terminal and try again."
            ],
        }]
    if skipped_parts:
        all_notes.insert(0, {
            "heading": "Large PDF Notice",
            "points": [
                f"This PDF was split into {total_parts} parts. "
                f"Only the first {MAX_PARTS} parts were processed "
                "because of free-tier AI limits.",
                "The notes below cover the beginning of the document only.",
            ],
        })


    return all_notes



def get_pdf_notes(material):
    key = f"[PDF] {material.title} (id {material.id})"

    saved = (
        SavedStudyNotes.objects.filter(topic=key)
        .order_by("-created_at")
        .first()
    )
    if saved:
        return saved.notes_json

    try:
        extracted_text = material.extracted_text.content
    except ExtractedMaterialText.DoesNotExist:
        with pymupdf.open(material.pdf_file.path) as pdf:
            extracted_text = "\n".join(
                page.get_text("text") for page in pdf
            ).strip()

    notes = generate_study_notes(extracted_text)

    bad_headings = ("Processing Notice", "Notes Could Not Be Generated")
    failed = any(
        isinstance(s, dict) and s.get("heading") in bad_headings
        for s in notes
    )
    if not failed:
        SavedStudyNotes.objects.create(
            topic=key,
            language="English",
            education_level="Not specified",
            purpose="All",
            notes_json=notes,
        )
    return notes


def create_notes(request, material_id):
    material = get_object_or_404(StudyMaterial, id=material_id)
    notes = get_pdf_notes(material)

    return render(
        request,
        "materials/notes.html",
        {
            "material": material,
            "notes": notes,
        },
    )

def generate_topic_notes(
    topic,
    language="English",
    education_level="College / University",
    purpose="All",
):
    import json
    import os

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return [{
            "heading": "Configuration Error",
            "points": ["GROQ_API_KEY is missing from the .env file."]
        }]

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=90.0,
        max_retries=1,
    )

    prompt = f"""
You are an expert teacher and textbook author.

Create a COMPLETE, DETAILED CHAPTER about:
{topic}

LEARNER PROFILE
- Language: {language}
- Education level: {education_level}
- Learning purpose: {purpose}

IMPORTANT:
This is topic-based learning, not PDF summarization.
Use your general knowledge to teach the topic thoroughly.
Never say the source does not contain information because no PDF
was supplied.

Write a textbook-style chapter, not a short summary.

Include these sections as relevant:
1. Chapter Overview
2. Learning Objectives
3. Prerequisites
4. Definitions and Terminology
5. Detailed Concepts and Explanations
6. Types and Classifications
7. Step-by-Step Working or Process
8. Examples with Explanations
9. Real-World Applications
10. Advantages and Limitations
11. Diagrams using clear text/ASCII where useful
12. Important Differences and Comparisons
13. Exam Questions with Model Answers
14. Multiple-Choice Questions with correct answers
15. Revision Points
16. Chapter Summary

Rules:
- Explain concepts thoroughly, with meaningful detail.
- Adapt the depth to the selected education level.
- Use the selected language consistently.
- Explain technical words before using them heavily.
- Include practical examples, not just definitions.
- Include code examples when relevant to the topic.
- For exam preparation, include short and long answers.
- For revision, include concise key points at the end.
- Avoid empty sections and repetitive filler.
- Do not invent citations, sources, or statistics.
- If a requested detail is uncertain, explain the uncertainty.
- Return valid JSON only in this format:
{{
  "sections": [
    {{
      "heading": "Section heading",
      "points": [
        "Detailed explanation...",
        "Example...",
        "Important point..."
      ]
    }}
  ]
}}

Make the chapter comprehensive and educational.
Do not replace detailed explanations with statements like
"no information is available."

Return JSON only.
"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a knowledgeable and patient teacher. "
                        "Create accurate, detailed educational chapters. "
                        "Return valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("The AI returned an empty response.")

        result = json.loads(content)
        sections = result.get("sections", [])

        if not isinstance(sections, list) or not sections:
            raise ValueError("The AI returned no usable chapter sections.")

        notes = []

        for section in sections:
            if not isinstance(section, dict):
                continue

            heading = section.get("heading", "Study Notes")
            points = section.get("points", [])

            if not isinstance(heading, str) or not isinstance(points, list):
                continue

            clean_points = [
                point.strip()
                for point in points
                if isinstance(point, str) and point.strip()
            ]

            if clean_points:
                notes.append({
                    "heading": heading,
                    "points": clean_points,
                })

        if not notes:
            raise ValueError("The AI response contained no usable notes.")

        return notes

    except Exception as error:
        print("Topic generation failed:", type(error).__name__)

        return [{
            "heading": "Notes Generation Failed",
            "points": [
                "The chapter could not be generated completely.",
                "Please try again. If the problem continues, check the server terminal.",
            ],
        }]



def clean_notes(notes):
    cleaned = []
    for section in notes:
        if not isinstance(section, dict):
            continue
        points = []
        for point in section.get("points", []):
            text = str(point).replace("\\n", "\n")
            text = re.sub(r"```[a-zA-Z]*", "", text)
            text = text.replace("```", "").strip()
            if text:
                points.append(text)
        cleaned.append({
            "heading": section.get("heading", ""),
            "points": points,
        })
    return cleaned


def delete_material(request, material_id):
    if request.method == "POST":
        material = get_object_or_404(StudyMaterial, id=material_id)

        key = f"[PDF] {material.title} (id {material.id})"
        SavedStudyNotes.objects.filter(topic=key).delete()

        if material.pdf_file:
            material.pdf_file.delete(save=False)
        material.delete()

        messages.success(request, "Study material deleted.")
    return redirect("upload_material")



def delete_saved_notes(request, notes_id):
    if request.method == "POST":
        item = get_object_or_404(SavedStudyNotes, id=notes_id)
        item.delete()
        messages.success(request, "Saved notes deleted.")
    return redirect("saved_notes_list")




def saved_notes_list(request):
    saved = SavedStudyNotes.objects.order_by("-created_at")
    return render(request, "materials/saved_list.html", {"saved": saved})


def saved_notes_detail(request, notes_id):
    item = get_object_or_404(SavedStudyNotes, id=notes_id)
    return render(
        request,
        "materials/topic.html",
        {
            "topic": item.topic,
            "notes": clean_notes(item.notes_json),
            "language": item.language,
            "education_level": item.education_level,
            "purpose": item.purpose,
        },
    )




def study_topic(request):
    notes = []
    topic = ""
    language = "English"
    education_level = "College / University"
    purpose = "All"

    if request.method == "POST":
        topic = request.POST.get("topic", "").strip()
        language = request.POST.get("language", "English").strip()
        education_level = request.POST.get(
            "education_level", "College / University"
        ).strip()
        purpose = request.POST.get("purpose", "All").strip()

        allowed_languages = ["English", "Hindi", "Hinglish"]
        allowed_levels = [
            "School",
            "College / University",
            "Competitive Exam",
            "Self-learning",
        ]
        allowed_purposes = [
            "Exam Preparation",
            "Conceptual Understanding",
            "Revision",
            "All",
        ]

        if not topic:
            messages.error(request, "Please enter a topic.")
        elif len(topic) > 300:
            messages.error(request, "Topic must be 300 characters or less.")
        elif language not in allowed_languages:
            messages.error(request, "Please select a valid language.")
        elif education_level not in allowed_levels:
            messages.error(request, "Please select a valid education level.")
        elif purpose not in allowed_purposes:
            messages.error(request, "Please select a valid learning purpose.")
        else:
            try:
                notes = generate_topic_notes(
                    topic=topic,
                    language=language,
                    education_level=education_level,
                    purpose=purpose,
                )
                notes = clean_notes(notes)

                failed = not notes or (
                    isinstance(notes[0], dict)
                    and notes[0].get("heading") == "Notes Generation Failed"
                                    
                )
                if not failed:
                    SavedStudyNotes.objects.create(
                        topic=topic,
                        language=language,
                        education_level=education_level,
                        purpose=purpose,
                        notes_json=notes,
                    )
                    messages.success(request, "Notes saved successfully.")

            except Exception as error:
                print("Topic study generation failed:", type(error).__name__)
                messages.error(
                    request,
                    "Study notes could not be generated. Please try again.",
                )

    return render(
        request,
        "materials/topic.html",
        {
            "topic": topic,
            "notes": notes,
            "language": language,
            "education_level": education_level,
            "purpose": purpose,
        },
    )


def download_notes_pdf(request, material_id):
    material = get_object_or_404(StudyMaterial, id=material_id)
    notes = get_pdf_notes(material)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(escape(material.title), styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Generated Study Notes", styles["Heading1"]))
    story.append(Spacer(1, 0.2 * inch))

    if isinstance(notes, str):
        story.append(
            Paragraph(
                escape(notes).replace("\n", "<br/>"),
                styles["BodyText"],
            )
        )
    else:
        for section in notes:
            heading = escape(str(section.get("heading", "Notes")))
            story.append(Paragraph(heading, styles["Heading2"]))

            for point in section.get("points", []):
                story.append(
                    Paragraph(
                        escape(str(point)).replace("\n", "<br/>"),
                        styles["BodyText"],
                    )
                )
                story.append(Spacer(1, 0.1 * inch))

    document.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="study_notes_{material.id}.pdf"'
    )
    return response


def generate_quiz_questions(notes, count=10, avoid=None):
    import json
    import random
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from the .env file.")

    source = build_quiz_source(notes.notes_json)
    if len(source) < 200:
        raise ValueError("Not enough notes text to make a quiz.")

    avoid = avoid or []
    avoid_text = ""
    if avoid:
        listed = "\n".join(f"- {q[:120]}" for q in avoid[-60:])
        avoid_text = (
            "\nThese questions already exist. Do NOT repeat or rephrase them:\n"
            f"{listed}\n"
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=90.0,
        max_retries=1,
    )

    prompt = f"""Create exactly {count} multiple-choice questions from the study notes below.

Rules:
- Each question has exactly 4 options and exactly one correct option.
- Test understanding of the concepts, not trivial wording.
- Cover different parts of the notes. Do not repeat questions.
- Write in {notes.language} (Hinglish means Hindi written in Roman script).
- Return valid JSON only, in this form:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "answer_index": 0, "explanation": "one short sentence"}}]}}
{avoid_text}
Topic: {notes.topic}

NOTES:
{source}
"""

    response = call_groq_with_retry(
        client,
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system",
             "content": "You are a careful exam setter. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty AI response.")

    data = json.loads(content)
    raw = data.get("questions", []) if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError("Unexpected AI response format.")

    norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()
    seen = {norm(q) for q in avoid}

    questions = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question", "")).strip()
        options = item.get("options")
        idx = item.get("answer_index")
        if (not q or not isinstance(options, list) or len(options) != 4
                or not isinstance(idx, int) or not 0 <= idx <= 3):
            continue
        options = [str(o).strip() for o in options]
        if not all(options) or len(set(options)) != 4:
            continue
        if norm(q) in seen:
            continue
        seen.add(norm(q))
        correct = options[idx]
        random.shuffle(options)
        questions.append({
            "question": q,
            "options": options,
            "answer_index": options.index(correct),
            "explanation": str(item.get("explanation", "")).strip(),
        })

    if len(questions) < max(3, count // 2):
        raise ValueError("Could not make a valid quiz. Please try again.")
    return questions[:count]


def get_or_create_quiz(notes):
    quiz = Quiz.objects.filter(notes=notes).first()
    if quiz:
        return quiz
    questions = generate_quiz_questions(notes, count=10)
    return Quiz.objects.create(notes=notes, questions_json=questions)


def add_more_questions(quiz, batch=10, limit=50):
    current = quiz.questions_json
    if len(current) >= limit:
        raise ValueError("Maximum of 50 questions reached.")
    want = min(batch, limit - len(current))
    new = generate_quiz_questions(
        quiz.notes, count=want, avoid=[q["question"] for q in current]
    )
    quiz.questions_json = current + new
    quiz.save()
    return len(new)


def quiz_home(request):
    rows = []
    for n in SavedStudyNotes.objects.order_by("-created_at"):
        quiz = Quiz.objects.filter(notes=n).first()
        best = None
        count = 0
        sizes = []
        if quiz:
            count = len(quiz.questions_json)
            sizes = list(range(5, count + 1, 5))
            if not sizes or sizes[-1] != count:
                sizes.append(count)
            attempts = list(quiz.attempts.all())
            if attempts:
                top = max(attempts, key=lambda a: a.score / a.total if a.total else 0)
                best = f"{top.score}/{top.total}"
        title = re.sub(r"^\[PDF\]\s*(.*?)\s*\(id \d+\)$", r"PDF: \1", n.topic)
        rows.append({
            "notes": n, "title": title, "has_quiz": bool(quiz), "best": best,
            "count": count, "sizes": sizes, "can_add": bool(quiz) and count < 50,
        })
    return render(request, "materials/quiz_home.html", {"rows": rows})


def quiz_take(request, notes_id):
    import random
    notes = get_object_or_404(SavedStudyNotes, id=notes_id)
    try:
        quiz = get_or_create_quiz(notes)
    except Exception as error:
        print("Quiz generation failed:", type(error).__name__, str(error)[:200])
        messages.error(
            request,
            f"Quiz could not be created ({type(error).__name__}: {str(error)[:120]}). "
            "Please try again in a minute.",
        )
        return redirect("quiz_home")

    questions = quiz.questions_json
    result = request.session.pop(f"quiz_result_{notes.id}", None)

    if request.method == "POST":
        picked = []
        for raw in request.POST.getlist("qi"):
            try:
                i = int(raw)
            except ValueError:
                continue
            if 0 <= i < len(questions) and i not in picked:
                picked.append(i)
        if not picked:
            messages.error(request, "Please start the quiz again.")
            return redirect("quiz_home")

        review = []
        score = 0
        for pos, i in enumerate(picked, start=1):
            q = questions[i]
            try:
                chosen = int(request.POST.get(f"a{i}", ""))
            except ValueError:
                chosen = None
            correct = q["answer_index"]
            if chosen == correct:
                score += 1
            review.append({
                "n": pos,
                "question": q["question"],
                "explanation": q.get("explanation", ""),
                "is_right": chosen == correct,
                "options": [
                    {"text": text, "is_correct": j == correct,
                     "is_chosen": j == chosen}
                    for j, text in enumerate(q["options"])
                ],
            })
        total = len(picked)
        QuizAttempt.objects.create(quiz=quiz, score=score, total=total)
        request.session[f"quiz_result_{notes.id}"] = {
            "score": score,
            "total": total,
            "percent": round(100 * score / total) if total else 0,
            "review": review,
        }
        return redirect("quiz_take", notes_id=notes.id)

    try:
        n = int(request.GET.get("n", 5))
    except ValueError:
        n = 5
    n = max(1, min(n, len(questions), 50))
    items = []
    if not result:
        picked = random.sample(range(len(questions)), n)
        items = [
            {"idx": i, "number": k, "question": questions[i]["question"],
             "options": questions[i]["options"]}
            for k, i in enumerate(picked, start=1)
        ]
    return render(request, "materials/quiz.html", {
        "notes": notes, "items": items, "result": result,
    })


def quiz_add_more(request, notes_id):
    if request.method != "POST":
        return redirect("quiz_home")
    notes = get_object_or_404(SavedStudyNotes, id=notes_id)
    quiz = Quiz.objects.filter(notes=notes).first()
    if not quiz:
        return redirect("quiz_home")
    try:
        added = add_more_questions(quiz)
        messages.success(
            request,
            f"{added} new questions added. Total: {len(quiz.questions_json)}.",
        )
    except Exception as error:
        print("Add questions failed:", type(error).__name__, str(error)[:200])
        messages.error(
            request,
            f"Could not add questions ({type(error).__name__}: {str(error)[:120]}). "
            "Please try again in a minute.",
        )
    return redirect("quiz_home")


def quiz_scores(request):
    attempts = list(
        QuizAttempt.objects.select_related("quiz__notes").order_by("-taken_at")[:100]
    )
    percents = []
    for a in attempts:
        a.percent = round(100 * a.score / a.total) if a.total else 0
        percents.append(a.percent)
    return render(request, "materials/quiz_scores.html", {
        "attempts": attempts,
        "taken": len(attempts),
        "best_pct": max(percents) if percents else 0,
        "avg_pct": round(sum(percents) / len(percents)) if percents else 0,
    })


def build_quiz_source(notes_json, max_chars=12000):
    parts = []
    for section in notes_json:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading", ""))
        low = heading.lower()
        if "multiple-choice" in low or "exam question" in low:
            continue
        points = " ".join(str(p) for p in section.get("points", []))
        parts.append(f"{heading}: {points}")
    return "\n".join(parts)[:max_chars]
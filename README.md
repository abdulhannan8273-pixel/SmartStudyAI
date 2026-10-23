# SmartStudy AI

AI-powered study assistant built with Django. Enter a topic or upload a PDF and get detailed, chapter-style study notes in English, Hindi or Hinglish. BCA industrial training project.

## Features (working now)

- Topic-only mode: generate a full chapter with language, education level and purpose options
- PDF upload with text extraction (PyMuPDF)
- AI notes generated from PDF text (chunked, Groq API)
- PDF download of generated notes (ReportLab)

## Planned features

- Save generated notes and reopen them without calling the AI again
- Saved notes library
- AI teacher chat (simplify, expand, examples, exam questions)
- Improved professional PDF export
- Quizzes / MCQs, scoring, revision planner, progress tracking

## Tech stack

- Python, Django, SQLite
- Groq API (OpenAI-compatible client), model `openai/gpt-oss-20b`
- PyMuPDF, ReportLab

## Setup (Windows, PowerShell)

```powershell
git clone https://github.com/abdulhannan8273-pixel/SmartStudyAI.git
cd SmartStudyAI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

Then run:

```powershell
python manage.py migrate
python manage.py runserver 8001
```

Open `http://127.0.0.1:8001/materials/topic/`

## Notes

- The `.env` file is private and is not committed to Git.
- Notes from topic-only mode come from the AI model's general knowledge and may contain mistakes.
- Scanned PDFs (images without text) are not supported yet.
- Free-tier Groq limits may apply.

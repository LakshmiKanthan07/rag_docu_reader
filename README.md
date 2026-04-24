# LangChain File Chatbot

A simple FastAPI + LangChain chatbot that accepts uploaded files, builds embeddings with FAISS, and answers questions from the document content.

## Features

- Upload arbitrary files from the browser
- Supports PDF, TXT, MD, HTML, CSV, JSON, DOCX, XLSX, and more
- Uses LangChain embeddings + FAISS for retrieval
- Provides a local frontend in `index.html`

## Requirements

- Python 3.10+ (recommended)
- `uvicorn`
- `fastapi`
- `langchain-ollama`
- `langchain-community`
- `langchain-text-splitters`
- `faiss-cpu`
- `python-docx`
- `openpyxl`

## Setup

1. Clone the repository.
2. Create a virtual environment:

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Copy the environment template:

```powershell
copy .env.template .env
```

5. Update `.env` with your API keys and preferred settings.

## Run the backend

```bash
uvicorn main:app --reload
```

## Run the frontend

```bash
python -m http.server 5500
```

Open `http://127.0.0.1:5500` in your browser, upload a file, then ask questions.

## Notes

- The backend currently uses `OllamaEmbeddings` and `ChatOllama`.
- Uploaded files are temporarily stored and removed after processing.
- Sessions are stored in memory for 24 hours by default.

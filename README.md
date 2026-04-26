# DocTalk API

A FastAPI + LangChain RAG service that accepts file uploads, builds FAISS vectorstores, and streams answers from document content using Ollama.

## Features

- Upload arbitrary files from the browser or API
- Supports PDF, TXT, MD, HTML, CSV, JSON, DOCX, XLSX, and more
- FAISS + LangChain embeddings for efficient retrieval
- Streaming responses with conversation history and citation sources
- Session-based isolation with TTL cleanup
- LRU in-memory cache for hot vectorstores
- Rate limiting and optional API key authentication
- Structured JSON logging

## Tech Stack

- **Backend**: FastAPI, Uvicorn
- **LLM**: Groq (`llama-3.3-70b-versatile` by default)
- **Embeddings**: Ollama (`nomic-embed-text` by default)
- **Vector Store**: FAISS (persisted to disk + in-memory LRU cache)
- **Document Loaders**: PyPDF, python-docx, openpyxl, CSV/JSON via langchain-community

## Requirements

- Python 3.10+
- Ollama running locally with `llama3` and `nomic-embed-text` models pulled

## Setup

1. Clone the repository.
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:

   ```bash
   copy .env.template .env
   ```

   Edit `.env` as needed (API_KEY, CORS_ORIGINS, model names, etc.).

## Run the backend

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

## Run the frontend

Open `index.html` in your browser (or serve it via any HTTP server):

```bash
python -m http.server 5500
```

Then open `http://127.0.0.1:5500` in your browser. The frontend is configured to connect to the API at `http://127.0.0.1:8000` by default (configurable in the HTML meta tags).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload a file → creates a new session |
| POST | `/ask` | Ask a question (streaming response) |
| DELETE | `/session/{session_id}` | Delete a session and its data |
| GET | `/health` | Health check |
| GET | `/metrics` | Operational metrics |

All endpoints except `/health` and `/metrics` require an API key (if configured) via `x-api-key` header.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | (none) | If set, all requests must include this key |
| `MAX_FILE_SIZE_MB` | `10` | Maximum upload size in MB |
| `CHUNK_SIZE` | `500` | Document chunk size for embeddings |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `TOP_K` | `5` | Number of context chunks retrieved per query |
| `SESSION_TTL_HOURS` | `24` | Session expiration time |
| `FAISS_PERSIST_DIR` | `./faiss_store` | Directory for persisted vectorstores |
| `VS_CACHE_SIZE` | `20` | Max sessions cached in RAM |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq chat model |
| `GROQ_API_KEY` | (none) | Groq API key (required) |
| `TEMPERATURE` | `0.3` | LLM temperature |
| `MAX_TOKENS` | `1024` | Max tokens per response |
| `CORS_ORIGINS` | `localhost:8000,5500` | Allowed CORS origins (comma-separated) |

## Notes

- Uploaded files are temporarily stored and removed after processing.
- Vectorstores are persisted to `FAISS_PERSIST_DIR` and kept in an LRU cache in RAM.
- Sessions expire after `SESSION_TTL_HOURS` of inactivity.
- The backend requires a running Ollama instance (for embeddings) and a Groq API key (for LLM inference).

   # DocTalk API v2.1.0

A FastAPI + LangChain RAG service that accepts file uploads, builds FAISS vectorstores, and streams answers from document content using Ollama.

## Features

- Upload multiple files from the browser or API
- Supports PDF, DOCX, XLSX, TXT, MD, HTML, CSV, JSON, and various code/text files
- FAISS + LangChain embeddings for efficient retrieval
- Streaming responses with conversation history and citation sources
- Session-based isolation with TTL cleanup and LRU caching
- Rate limiting and optional API key authentication
- Structured JSON logging
- CORS support for web frontend

## Tech Stack

- **Backend**: FastAPI, Uvicorn
- **LLM**: Groq (`llama-3.3-70b-versatile` by default)
- **Embeddings**: Ollama (`nomic-embed-text` by default)
- **Vector Store**: FAISS (persisted to disk + in-memory LRU cache)
- **Document Loaders**: PyPDF, python-docx, openpyxl, CSV/JSON via langchain-community
- **Frontend**: Vanilla HTML/CSS/JS (no frameworks)

## Requirements

- Python 3.10+
- Ollama running locally with embedding and chat models pulled
- Groq API key for LLM access

## Setup

1. Clone the repository.
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   source .venv/bin/activate  # macOS/Linux
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set up Ollama (if not already running):

   ```bash
   ollama pull nomic-embed-text
   ollama pull llama3.2  # or your preferred model
   ```

5. Configure environment variables:

   Create a `.env` file (copy from `.env.template` if available):

   ```bash
   GROQ_API_KEY=your_groq_api_key_here
   # Optional: API_KEY=your_optional_api_key
   # Optional: CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
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
   | POST | `/upload` | Upload multiple files → creates a new session with merged vectorstore |
   | POST | `/ask` | Ask a question (streaming response with citations) |
   | DELETE | `/session/{session_id}` | Delete a session and its data |
   | GET | `/health` | Health check with timestamp and session count |
   | GET | `/metrics` | Operational metrics (uploads, questions, sessions) |

   All endpoints except `/health` and `/metrics` require an API key (if configured) via `x-api-key` header.

   ## Supported File Types

   - **Documents**: PDF, DOCX, XLSX
   - **Text**: TXT, MD, HTML, HTM, LOG, XML, YAML, YML, TOML, INI, CFG
   - **Code**: PY, JAVA, JS, TS, CSS, SCSS
   - **Data**: CSV, JSON

   Maximum file size: 50 MB per file (configurable)

   ## Environment Variables

   | Variable | Default | Description |
   |----------|---------|-------------|
   | `API_KEY` | (none) | If set, all requests must include this key in `x-api-key` header |
   | `MAX_FILE_SIZE_MB` | `50` | Maximum upload size per file in MB |
   | `MAX_FILES_PER_UPLOAD` | `0` | Maximum files per upload (0 = no limit) |
   | `CHUNK_SIZE` | `500` | Document chunk size for embeddings |
   | `CHUNK_OVERLAP` | `50` | Overlap between chunks |
   | `TOP_K` | `5` | Number of context chunks retrieved per query |
   | `SESSION_TTL_HOURS` | `24` | Session expiration time in hours |
   | `FAISS_PERSIST_DIR` | `./faiss_store` | Directory for persisted vectorstores |
   | `VS_CACHE_SIZE` | `20` | Max sessions cached in RAM (LRU) |
   | `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
   | `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq chat model |
   | `GROQ_API_KEY` | (required) | Groq API key |
   | `TEMPERATURE` | `0.3` | LLM temperature |
   | `MAX_TOKENS` | `1024` | Max tokens per response |
   | `CORS_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500` | Allowed CORS origins (comma-separated) |

   ## Notes

   - Uploaded files are temporarily stored and removed after processing.
   - Vectorstores are persisted to `FAISS_PERSIST_DIR` and kept in an LRU cache in RAM.
   - Sessions expire after `SESSION_TTL_HOURS` of inactivity.
   - The backend requires a running Ollama instance (for embeddings) and a Groq API key (for LLM inference).

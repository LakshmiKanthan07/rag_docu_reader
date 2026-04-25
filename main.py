import os
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

from dotenv import load_dotenv
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
import uuid

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader, CSVLoader, JSONLoader
from langchain_core.documents.base import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
import docx
import openpyxl

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Config ────────────────────────────────────────────────────────────────────
MAX_FILE_SIZE     = int(os.getenv("MAX_FILE_SIZE_MB", "10")) * 1024 * 1024
CHUNK_SIZE        = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP     = int(os.getenv("CHUNK_OVERLAP", "100"))
TOP_K             = int(os.getenv("TOP_K", "5"))
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
PERSIST_DIR       = os.getenv("FAISS_PERSIST_DIR", "./faiss_store")
API_KEY           = os.getenv("API_KEY", "")   # empty string = auth disabled

ALLOWED_EXTENSIONS = {
    ".pdf", ".csv", ".json",
    ".txt", ".md", ".html", ".htm", ".log", ".xml",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".java", ".js", ".ts", ".css", ".scss",
    ".docx", ".xlsx",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".log", ".xml",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".java", ".js", ".ts", ".css", ".scss",
}

os.makedirs(PERSIST_DIR, exist_ok=True)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="DocTalk API",
    description="Upload files and chat with their content — streaming, memory, persistent storage.",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Auth dependency ───────────────────────────────────────────────────────────
def require_api_key(request: Request) -> None:
    """Soft API-key guard — disabled when API_KEY env var is unset."""
    if not API_KEY:
        return
    if request.headers.get("x-api-key", "") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

# ── LLM & Embeddings ──────────────────────────────────────────────────────────
embeddings = OllamaEmbeddings(model=os.getenv("EMBED_MODEL", "nomic-embed-text"))

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "llama3"),
    temperature=float(os.getenv("TEMPERATURE", "0.3")),
    num_predict=int(os.getenv("NUM_PREDICT", "512")),
)

# ── Improved RAG prompt ───────────────────────────────────────────────────────
RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are a precise document assistant. Answer questions strictly from the context below.

Rules:
- Use ONLY the provided context. No outside knowledge.
- If the answer is absent from the context, say: "I don't know based on the provided document."
- Be concise and direct. Skip filler like "Based on the context...".
- Cite the relevant part of the document when it strengthens your answer.
- Never guess, infer beyond the text, or hallucinate.

--- DOCUMENT CONTEXT ---
{context}
--- END CONTEXT ---

Conversation history:
{history}

User: {question}
Assistant:"""
)

# ── Session store ─────────────────────────────────────────────────────────────
class SessionStore:
    """
    Registry of active sessions.
    Vectorstores are persisted to disk (FAISS save_local/load_local).
    Chat history is kept in memory (last 20 turns per session).
    """

    def __init__(self, ttl_hours: int = 24) -> None:
        self._meta: Dict[str, dict] = {}   # session_id → {created_at, history}
        self._ttl  = timedelta(hours=ttl_hours)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._start_cleanup_thread()
        logger.info("SessionStore ready (TTL=%dh, dir=%s)", ttl_hours, PERSIST_DIR)

    # ── public ────────────────────────────────────────────────

    def create(self, session_id: str, vectorstore: FAISS) -> None:
        vectorstore.save_local(self._path(session_id))
        with self._lock:
            self._meta[session_id] = {"created_at": datetime.now(), "history": []}
        logger.info("Session created: %s", session_id[:8])

    def get_vectorstore(self, session_id: str) -> FAISS:
        self._validate(session_id)
        path = self._path(session_id)
        if not os.path.isdir(path):
            raise HTTPException(status_code=404, detail="Session data missing on disk.")
        return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)

    def get_history(self, session_id: str) -> List[dict]:
        self._validate(session_id)
        with self._lock:
            return list(self._meta[session_id]["history"])

    def append_history(self, session_id: str, role: str, content: str) -> None:
        self._validate(session_id)
        with self._lock:
            hist = self._meta[session_id]["history"]
            hist.append({"role": role, "content": content})
            # cap at 20 turns to avoid context overflow
            self._meta[session_id]["history"] = hist[-20:]

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._meta.pop(session_id, None)
        import shutil as _shutil
        path = self._path(session_id)
        if os.path.isdir(path):
            _shutil.rmtree(path, ignore_errors=True)
        logger.info("Session removed: %s", session_id[:8])

    def shutdown(self) -> None:
        self._stop.set()

    # ── private ───────────────────────────────────────────────

    def _path(self, session_id: str) -> str:
        return os.path.join(PERSIST_DIR, session_id)

    def _validate(self, session_id: str) -> None:
        with self._lock:
            meta = self._meta.get(session_id)
        if meta is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found or expired. Please upload the file again.",
            )
        if datetime.now() - meta["created_at"] >= self._ttl:
            self.remove(session_id)
            raise HTTPException(
                status_code=404,
                detail="Session expired. Please upload the file again.",
            )

    def _cleanup(self) -> None:
        with self._lock:
            now = datetime.now()
            expired = [sid for sid, m in self._meta.items() if now - m["created_at"] >= self._ttl]
        for sid in expired:
            self.remove(sid)
        if expired:
            logger.info("Cleaned up %d expired session(s).", len(expired))

    def _start_cleanup_thread(self) -> None:
        def loop():
            while not self._stop.wait(3600):
                self._cleanup()
        threading.Thread(target=loop, daemon=True).start()


sessions = SessionStore(ttl_hours=SESSION_TTL_HOURS)

# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    try:
        embeddings.embed_query("ping")
        logger.info("Ollama embeddings reachable.")
    except Exception as exc:
        logger.error("Ollama unreachable at startup: %s", exc)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    sessions.shutdown()
    logger.info("SessionStore shut down cleanly.")

# ── Document loaders ──────────────────────────────────────────────────────────
def load_text_file(path: str) -> List[Document]:
    return TextLoader(path, encoding="utf-8").load()

def load_docx_file(path: str) -> List[Document]:
    d = docx.Document(path)
    parts: List[str] = []
    for para in d.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append("\t".join(cells))
    content = "\n\n".join(parts).strip()
    return [Document(page_content=content)] if content else []

def load_xlsx_file(path: str) -> List[Document]:
    wb = openpyxl.load_workbook(path, data_only=True)
    parts: List[str] = []
    for sheet in wb.worksheets:
        rows = ["\t".join("" if v is None else str(v) for v in row)
                for row in sheet.iter_rows(values_only=True)]
        if any(r.strip() for r in rows):
            parts.append(f"Sheet: {sheet.title}\n" + "\n".join(rows))
    content = "\n\n".join(parts).strip()
    return [Document(page_content=content)] if content else []

LOADER_MAP = {
    ".pdf":  lambda p: PyPDFLoader(p).load(),
    ".csv":  lambda p: CSVLoader(p).load(),
    ".json": lambda p: JSONLoader(p, jq_schema=".", text_content=False).load(),
    ".docx": load_docx_file,
    ".xlsx": load_xlsx_file,
    **{ext: load_text_file for ext in TEXT_EXTENSIONS},
}

def load_documents(file_path: str, filename: str) -> List[Document]:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    loader = LOADER_MAP.get(ext)
    if loader is None:
        raise HTTPException(status_code=415, detail=f"No loader configured for '{ext}'.")
    return loader(file_path)

def cleanup_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as exc:
        logger.warning("Could not delete temp file %s: %s", path, exc)

# ── /upload ───────────────────────────────────────────────────────────────────
@app.post("/upload", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def upload_file(request: Request, file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_FILE_SIZE // (1024*1024)} MB limit.",
        )

    ext = os.path.splitext(file.filename)[1].lower() or ".txt"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: '{ext}'.")

    session_id = str(uuid.uuid4())
    tmp_path: Optional[str] = None

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        docs = load_documents(tmp_path, file.filename)
        if not docs:
            raise HTTPException(status_code=422, detail="Could not extract text from file.")

        splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        chunks = splitter.split_documents(docs)
        if not chunks:
            raise HTTPException(status_code=422, detail="File appears empty after processing.")

        vectorstore = FAISS.from_documents(chunks, embeddings)
        sessions.create(session_id, vectorstore)

        logger.info("Upload OK — session=%s file=%s chunks=%d", session_id[:8], file.filename, len(chunks))
        return {"message": "File processed successfully.", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload error for file: %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Processing error: {exc}")
    finally:
        if tmp_path:
            cleanup_file(tmp_path)

# ── /ask  (streaming) ─────────────────────────────────────────────────────────
class Query(BaseModel):
    question: str
    session_id: str

    @field_validator("question")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty.")
        return v


def _fmt_history(history: List[dict]) -> str:
    if not history:
        return "(no prior conversation)"
    return "\n".join(
        f"{'User' if h['role'] == 'human' else 'Assistant'}: {h['content']}"
        for h in history
    )


@app.post("/ask", dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
async def ask_question(request: Request, query: Query) -> StreamingResponse:
    # ③ Query logging
    logger.info("Question — session=%s q=%r", query.session_id[:8], query.question)

    vectorstore = sessions.get_vectorstore(query.session_id)
    history     = sessions.get_history(query.session_id)

    docs    = vectorstore.as_retriever(search_kwargs={"k": TOP_K}).invoke(query.question)
    context = "\n\n".join(d.page_content for d in docs)

    final_prompt = RAG_PROMPT.invoke({
        "context":  context,
        "history":  _fmt_history(history),
        "question": query.question,
    })

    sessions.append_history(query.session_id, "human", query.question)

    async def stream_tokens():
        collected: List[str] = []
        try:
            for chunk in llm.stream(final_prompt):
                token = chunk.content
                if token:
                    collected.append(token)
                    yield token
        except Exception as exc:
            logger.exception("Streaming error — session=%s", query.session_id[:8])
            yield f"\n[ERROR: {exc}]"
        finally:
            sessions.append_history(query.session_id, "assistant", "".join(collected))

    return StreamingResponse(stream_tokens(), media_type="text/plain")


# ── /session/{id}  DELETE ─────────────────────────────────────────────────────
@app.delete("/session/{session_id}", dependencies=[Depends(require_api_key)])
async def delete_session(session_id: str) -> dict:
    sessions.remove(session_id)
    return {"message": "Session deleted."}


# ── /health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

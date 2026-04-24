import os
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import threading

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import shutil
import uuid

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader, CSVLoader, JSONLoader
from langchain_core.documents.base import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
import docx
import openpyxl

app = FastAPI(title="File Chatbot API", description="Upload files and ask questions about their content")

# CORS middleware — origins from env var for easy prod config
origins = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# File constraints
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "10")) * 1024 * 1024  # Default 10 MB

# Allowlisted extensions only — no generic fallback
ALLOWED_EXTENSIONS = {
    ".pdf", ".csv", ".json",
    ".txt", ".md", ".html", ".htm", ".log", ".xml",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".java", ".js", ".ts", ".css", ".scss",
    ".docx", ".xlsx",
}


class SessionStore:
    def __init__(self, ttl_hours: int = 24):
        self.sessions: Dict[str, dict] = {}
        self.ttl = ttl_hours * 3600
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._start_cleanup_thread()
        logger.info(f"Session store initialized with TTL: {ttl_hours} hours")

    def add(self, session_id: str, vectorstore: FAISS) -> None:
        with self._lock:
            self.sessions[session_id] = {
                "vectorstore": vectorstore,
                "created_at": datetime.now()
            }
        logger.info(f"Session added: {session_id}")

    def get(self, session_id: str) -> Optional[FAISS]:
        with self._lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                if datetime.now() - session["created_at"] < timedelta(seconds=self.ttl):
                    return session["vectorstore"]
                else:
                    logger.info(f"Session expired: {session_id}")
                    del self.sessions[session_id]
        return None

    def remove(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Session removed: {session_id}")
                return True
        return False

    def _cleanup_old_sessions(self) -> None:
        with self._lock:
            current_time = datetime.now()
            expired = [
                sid for sid, sess in self.sessions.items()
                if current_time - sess["created_at"] >= timedelta(seconds=self.ttl)
            ]
            for sid in expired:
                del self.sessions[sid]
                logger.info(f"Cleaned up expired session: {sid}")

    def _start_cleanup_thread(self) -> None:
        def cleanup_loop():
            # Uses event.wait so it can be stopped gracefully on shutdown
            while not self._stop_event.wait(3600):
                self._cleanup_old_sessions()
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()


vectorstores = SessionStore(ttl_hours=int(os.getenv("SESSION_TTL_HOURS", "24")))

embeddings = OllamaEmbeddings(model=os.getenv("EMBED_MODEL", "nomic-embed-text"))

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "llama3"),
    temperature=float(os.getenv("TEMPERATURE", "0.3")),
    num_predict=int(os.getenv("NUM_PREDICT", "200"))
)

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
TOP_K = int(os.getenv("TOP_K", "5"))

prompt = ChatPromptTemplate.from_template(
    """
You are a helpful assistant.

Rules:
- Answer ONLY using the context
- If answer not found → say "I don't know"
- Do NOT hallucinate

Context:
{context}

Question:
{question}
"""
)


# ── Startup health check ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_check():
    try:
        embeddings.embed_query("ping")
        logger.info("Ollama embeddings reachable at startup.")
    except Exception as e:
        logger.error(f"Ollama unreachable at startup — check OLLAMA_MODEL / EMBED_MODEL config: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    vectorstores.shutdown()
    logger.info("Session store shut down cleanly.")


# ── Document loaders ──────────────────────────────────────────────────────────

def load_text_file(file_path: str) -> List[Document]:
    loader = TextLoader(file_path, encoding="utf-8")
    return loader.load()


def load_docx_file(file_path: str) -> List[Document]:
    doc = docx.Document(file_path)
    parts: List[str] = []
    for para in doc.paragraphs:
        if para.text:
            parts.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            row_values = [cell.text.strip() for cell in row.cells]
            if any(row_values):
                parts.append("\t".join(row_values))
    content = "\n\n".join(parts).strip()
    return [Document(page_content=content)] if content else []


def load_xlsx_file(file_path: str) -> List[Document]:
    workbook = openpyxl.load_workbook(file_path, data_only=True)
    parts: List[str] = []
    for sheet in workbook.worksheets:
        rows: List[str] = []
        for row in sheet.iter_rows(values_only=True):
            rows.append("\t".join("" if v is None else str(v) for v in row))
        if any(line.strip() for line in rows):
            parts.append(f"Sheet: {sheet.title}\n" + "\n".join(rows))
    content = "\n\n".join(parts).strip()
    return [Document(page_content=content)] if content else []


# Dispatch table — clean, extensible, no long if-elif chains
TEXT_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".log", ".xml",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".java", ".js", ".ts", ".css", ".scss",
}

LOADER_DISPATCH = {
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
        raise HTTPException(status_code=415, detail=f"Unsupported file type: '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    loader = LOADER_DISPATCH.get(ext)
    if loader is None:
        raise HTTPException(status_code=415, detail=f"No loader configured for: '{ext}'")
    return loader(file_path)


def cleanup_file(file_path: str) -> None:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file {file_path}: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Read entire file into memory first so we can enforce size limit
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE // (1024 * 1024)} MB."
        )

    extension = os.path.splitext(file.filename)[1].lower() or ".txt"

    # Validate extension before touching disk
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: '{extension}'")

    session_id = str(uuid.uuid4())
    file_path: Optional[str] = None

    try:
        # Write to a proper temp file, not the CWD
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
            tmp.write(contents)
            file_path = tmp.name

        documents = load_documents(file_path, file.filename)
        if not documents:
            raise HTTPException(status_code=400, detail="Failed to extract text from the uploaded file.")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_documents(documents)

        if not chunks:
            raise HTTPException(status_code=400, detail="No text content found in the uploaded file.")

        vectorstore = FAISS.from_documents(chunks, embeddings)
        vectorstores.add(session_id, vectorstore)

        return {
            "message": "File uploaded & processed successfully",
            "session_id": session_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during file upload")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    finally:
        if file_path:
            cleanup_file(file_path)


class Query(BaseModel):
    question: str
    session_id: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Question cannot be empty")
        return v.strip()


@app.post("/ask")
async def ask_question(query: Query):
    vectorstore = vectorstores.get(query.session_id)
    if not vectorstore:
        raise HTTPException(
            status_code=404,
            detail="Invalid or expired session. Please upload the file again."
        )

    try:
        retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
        docs = retriever.invoke(query.question)

        context = "\n\n".join(doc.page_content for doc in docs)

        final_prompt = prompt.invoke({
            "context": context,
            "question": query.question,
        })

        response = llm.invoke(final_prompt)
        return {"answer": response.content}
    except Exception as e:
        logger.exception("Unexpected error while generating answer")
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

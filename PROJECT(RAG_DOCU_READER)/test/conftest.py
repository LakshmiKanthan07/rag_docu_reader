"""
conftest.py — Shared test environment for DocTalk API
======================================================
Provides:
  - Isolated FastAPI test client
  - Mocked LLM (ChatGroq) and Embeddings (OllamaEmbeddings)
  - In-memory FAISS vectorstore helpers
  - Reusable file fixtures (txt, pdf-stub, docx-stub, etc.)
  - Temporary FAISS_PERSIST_DIR so tests never touch real data
"""
import io
import os
import shutil
import tempfile
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from typing import Generator, List

_tmp_persist = tempfile.mkdtemp(prefix="doctalk_test_")
os.environ.setdefault("FAISS_PERSIST_DIR", _tmp_persist)
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
os.environ.setdefault("SESSION_TTL_HOURS", "1")
os.environ.setdefault("TESTING", "1")

from fastapi.testclient import TestClient
from langchain_core.documents.base import Document

from rag_docu_reader import main  

def _make_fake_vectorstore(docs: List[Document] = None):
    """Return a real in-memory FAISS store seeded with trivial content."""
    from langchain_community.vectorstores import FAISS
    from langchain_core.embeddings import FakeEmbeddings

    if docs is None:
        docs = [
            Document(page_content="The sky is blue.", metadata={"source": "test.txt", "page": 1}),
            Document(page_content="Python is a programming language.", metadata={"source": "test.txt", "page": 2}),
        ]
    fake_emb = FakeEmbeddings(size=768)
    return FAISS.from_documents(docs, fake_emb)


def _fake_embed_query(text: str) -> List[float]:
    """Deterministic 768-d zero vector (fast, no Ollama needed)."""
    return [0.0] * 768


def _fake_embed_documents(texts: List[str]) -> List[List[float]]:
    return [[0.0] * 768 for _ in texts]

@pytest.fixture(scope="session", autouse=True)
def cleanup_persist_dir():
    """Remove the temp FAISS dir after the entire test session."""
    yield
    shutil.rmtree(_tmp_persist, ignore_errors=True)


@pytest.fixture(autouse=True)
def mock_embeddings(monkeypatch):
    """
    Replace OllamaEmbeddings with a fast, offline stub.
    Applied automatically to every test so no Ollama process is needed.
    """
    from langchain_core.embeddings import FakeEmbeddings
    mock_emb = FakeEmbeddings(size=768)
    monkeypatch.setattr(main, "embeddings", mock_emb)
    return mock_emb

@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """
    Replace ChatGroq with a stub that streams a fixed reply.
    Applied automatically to every test so no Groq API key is needed.
    """
    async def _fake_astream(prompt, **kwargs):
        tokens = ["This ", "is ", "a ", "mocked ", "answer."]
        for t in tokens:
            chunk = MagicMock()
            chunk.content = t
            yield chunk

    mock_llm_obj = MagicMock()
    mock_llm_obj.astream = _fake_astream
    monkeypatch.setattr(main, "llm", mock_llm_obj)
    return mock_llm_obj


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """
    TestClient wrapping the FastAPI app.
    API_KEY auth is disabled (empty string) so tests don't need headers.
    """
    with patch.object(main, "API_KEY", ""):
        with TestClient(main.app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture()
def authed_client() -> Generator[TestClient, None, None]:
    """TestClient with a fixed API key for auth-related tests."""
    with patch.object(main, "API_KEY", "secret-test-key"):
        with TestClient(main.app, raise_server_exceptions=True) as c:
            yield c


# ── File content helpers ──────────────────────────────────────────────────────

@pytest.fixture()
def txt_file() -> tuple[str, bytes, str]:
    """(filename, content_bytes, mime_type)"""
    content = b"The quick brown fox jumps over the lazy dog.\nThis document is about animals."
    return ("test.txt", content, "text/plain")


@pytest.fixture()
def md_file() -> tuple[str, bytes, str]:
    content = b"# Title\n\nSome **markdown** content about Python testing.\n"
    return ("readme.md", content, "text/markdown")


@pytest.fixture()
def large_file() -> tuple[str, bytes, str]:
    """File just over the 50 MB default limit."""
    content = b"x" * (51 * 1024 * 1024)
    return ("big.txt", content, "text/plain")


@pytest.fixture()
def empty_file() -> tuple[str, bytes, str]:
    return ("empty.txt", b"", "text/plain")


@pytest.fixture()
def unsupported_file() -> tuple[str, bytes, str]:
    return ("malware.exe", b"\x4d\x5a\x00\x00", "application/octet-stream")


@pytest.fixture()
def csv_file() -> tuple[str, bytes, str]:
    content = b"name,age,city\nAlice,30,Paris\nBob,25,London\n"
    return ("data.csv", content, "text/csv")


@pytest.fixture()
def json_file() -> tuple[str, bytes, str]:
    content = b'[{"id": 1, "topic": "machine learning"}, {"id": 2, "topic": "deep learning"}]'
    return ("data.json", content, "application/json")


# ── Session helper ────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded_session(client, txt_file) -> str:
    """
    Upload a real txt file, return the session_id.
    Useful for /ask and vectorstore tests that need a pre-existing session.
    """
    filename, content, mime = txt_file
    resp = client.post(
        "/upload",
        files=[("files", (filename, io.BytesIO(content), mime))],
    )
    assert resp.status_code == 200, f"seed upload failed: {resp.text}"
    return resp.json()["session_id"]
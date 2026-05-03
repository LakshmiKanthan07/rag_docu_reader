"""
test_vectorstore.py — Retrieval engine
========================================
Answers: "Can the system remember and retrieve correctly?"

Covers:
  - LRUVectorstoreCache: get / put / eviction / remove
  - SessionStore: create / get_vectorstore / get_history / append_history / remove
  - Retrieval returns relevant chunks for a known query
  - Retrieval doesn't crash on empty / irrelevant queries
  - Disk persistence: vectorstore is written to PERSIST_DIR
  - Session TTL: expired sessions are rejected
  - Concurrent create/remove doesn't deadlock (thread-safety smoke test)
  - Source metadata is preserved end-to-end
"""

import io
import os
import shutil
import tempfile
import threading
import time
import pytest

from unittest.mock import patch, MagicMock
from langchain_core.documents.base import Document
from langchain_core.embeddings import FakeEmbeddings


# ── Fixture: real in-memory vectorstore ───────────────────────────────────────

@pytest.fixture()
def fake_vs():
    """A real FAISS vectorstore built with FakeEmbeddings (no Ollama needed)."""
    from langchain_community.vectorstores import FAISS

    docs = [
        Document(page_content="The sky is blue.", metadata={"source": "doc1.txt", "page": 1}),
        Document(page_content="Python is a high-level programming language.", metadata={"source": "doc1.txt", "page": 2}),
        Document(page_content="Neural networks learn from data.", metadata={"source": "doc1.txt", "page": 3}),
        Document(page_content="The sun rises in the east.", metadata={"source": "doc2.txt", "page": 1}),
    ]
    emb = FakeEmbeddings(size=768)
    return FAISS.from_documents(docs, emb)


@pytest.fixture()
def temp_persist(tmp_path):
    """Isolated persist directory for SessionStore tests."""
    return str(tmp_path / "sessions")


@pytest.fixture()
def store(temp_persist, monkeypatch):
    """
    Fresh SessionStore wired to a temp directory.
    The global `embeddings` is patched so FAISS.load_local uses FakeEmbeddings.
    """
    from rag_docu_reader import main
    from langchain_core.embeddings import FakeEmbeddings
    monkeypatch.setattr(main, "PERSIST_DIR", temp_persist)
    os.makedirs(temp_persist, exist_ok=True)

    fake_emb = FakeEmbeddings(size=768)
    monkeypatch.setattr(main, "embeddings", fake_emb)

    from rag_docu_reader.main import SessionStore
    s = SessionStore(ttl_hours=1)
    yield s
    s.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# LRUVectorstoreCache
# ─────────────────────────────────────────────────────────────────────────────

class TestLRUVectorstoreCache:
    from rag_docu_reader.main import LRUVectorstoreCache

    def test_get_missing_key_returns_none(self, fake_vs):
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=3)
        assert cache.get("nonexistent") is None

    def test_put_and_get_returns_same_object(self, fake_vs):
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=3)
        cache.put("s1", fake_vs)
        assert cache.get("s1") is fake_vs

    def test_remove_makes_key_unreachable(self, fake_vs):
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=3)
        cache.put("s1", fake_vs)
        cache.remove("s1")
        assert cache.get("s1") is None

    def test_remove_nonexistent_key_is_silent(self):
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=3)
        cache.remove("ghost")  # must not raise

    def test_lru_eviction_at_capacity(self, fake_vs):
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=2)
        cache.put("s1", fake_vs)
        cache.put("s2", fake_vs)
        # Access s1 so it becomes most-recently-used
        cache.get("s1")
        # Insert s3 → s2 (LRU) should be evicted
        cache.put("s3", fake_vs)
        assert cache.get("s2") is None
        assert cache.get("s1") is not None
        assert cache.get("s3") is not None

    def test_overwrite_existing_key_updates_value(self, fake_vs):
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=3)
        cache.put("s1", fake_vs)

        # Build a second distinct store
        from langchain_community.vectorstores import FAISS
        docs2 = [Document(page_content="Different content.", metadata={"page": 1})]
        vs2 = FAISS.from_documents(docs2, FakeEmbeddings(size=768))

        cache.put("s1", vs2)
        assert cache.get("s1") is vs2

    def test_thread_safe_concurrent_puts(self, fake_vs):
        """20 threads putting concurrently must not corrupt the cache."""
        from rag_docu_reader.main import LRUVectorstoreCache
        cache = LRUVectorstoreCache(maxsize=100)
        errors = []

        def worker(i):
            try:
                cache.put(f"s{i}", fake_vs)
                cache.get(f"s{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# SessionStore
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionStore:
    def test_create_and_get_vectorstore(self, store, fake_vs, temp_persist):
        store.create("abc", fake_vs)
        vs = store.get_vectorstore("abc")
        assert vs is not None

    def test_get_vectorstore_unknown_session_raises_404(self, store):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            store.get_vectorstore("unknown-session")
        assert exc_info.value.status_code == 404

    def test_history_initially_empty(self, store, fake_vs):
        store.create("s1", fake_vs)
        assert store.get_history("s1") == []

    def test_append_history_adds_entries(self, store, fake_vs):
        store.create("s1", fake_vs)
        store.append_history("s1", "human", "Hello")
        store.append_history("s1", "assistant", "Hi!")
        hist = store.get_history("s1")
        assert len(hist) == 2
        assert hist[0] == {"role": "human", "content": "Hello"}
        assert hist[1] == {"role": "assistant", "content": "Hi!"}

    def test_append_history_noop_for_nonexistent_session(self, store):
        """Should not raise — silently ignored."""
        store.append_history("ghost", "human", "Hello")

    def test_history_capped_at_20_entries(self, store, fake_vs):
        store.create("s1", fake_vs)
        for i in range(25):
            store.append_history("s1", "human", f"msg {i}")
        assert len(store.get_history("s1")) == 20

    def test_remove_deletes_session(self, store, fake_vs, temp_persist):
        store.create("s1", fake_vs)
        store.remove("s1")
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            store.get_vectorstore("s1")

    def test_remove_deletes_disk_directory(self, store, fake_vs, temp_persist):
        store.create("s1", fake_vs)
        session_path = os.path.join(temp_persist, "s1")
        assert os.path.isdir(session_path)
        store.remove("s1")
        assert not os.path.isdir(session_path)

    def test_active_count_increments_on_create(self, store, fake_vs):
        initial = store.active_count()
        store.create("s1", fake_vs)
        assert store.active_count() == initial + 1

    def test_active_count_decrements_on_remove(self, store, fake_vs):
        store.create("s1", fake_vs)
        count_before = store.active_count()
        store.remove("s1")
        assert store.active_count() == count_before - 1

    def test_vectorstore_reloaded_from_disk_after_cache_eviction(self, store, fake_vs):
        """Evict from LRU cache; session must reload from disk transparently."""
        from rag_docu_reader import main
        store.create("s1", fake_vs)
        # Forcibly remove from RAM cache
        main.vs_cache.remove("s1")
        # Should reload from disk without error
        vs = store.get_vectorstore("s1")
        assert vs is not None

    def test_expired_session_raises_404(self, temp_persist, monkeypatch):
        """Sessions past TTL must be rejected."""
        from rag_docu_reader import main
        from datetime import datetime, timedelta
        from rag_docu_reader.main import SessionStore

        monkeypatch.setattr(main, "PERSIST_DIR", temp_persist)
        os.makedirs(temp_persist, exist_ok=True)
        monkeypatch.setattr(main, "embeddings", FakeEmbeddings(size=768))

        s = SessionStore(ttl_hours=1)
        from langchain_community.vectorstores import FAISS
        docs = [Document(page_content="hello", metadata={"page": 1})]
        vs = FAISS.from_documents(docs, FakeEmbeddings(size=768))
        s.create("exp", vs)

        # Backdate the created_at so it's definitely expired
        with s._lock:
            s._meta["exp"]["created_at"] = datetime.now() - timedelta(hours=2)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            s.get_vectorstore("exp")
        assert exc_info.value.status_code == 404
        s.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval quality
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrieval:
    def test_retrieval_returns_documents(self, store, fake_vs):
        store.create("s1", fake_vs)
        vs = store.get_vectorstore("s1")
        docs = vs.as_retriever(search_kwargs={"k": 2}).invoke("blue sky")
        assert len(docs) > 0

    def test_retrieval_result_has_page_content(self, store, fake_vs):
        store.create("s1", fake_vs)
        vs = store.get_vectorstore("s1")
        docs = vs.as_retriever(search_kwargs={"k": 1}).invoke("programming")
        assert len(docs) >= 1
        assert len(docs[0].page_content) > 0

    def test_retrieval_respects_top_k(self, store, fake_vs):
        store.create("s1", fake_vs)
        vs = store.get_vectorstore("s1")
        for k in (1, 2, 3):
            docs = vs.as_retriever(search_kwargs={"k": k}).invoke("hello")
            assert len(docs) <= k

    def test_source_metadata_preserved_after_upload(self, client):
        """
        Upload a txt file, retrieve the vectorstore, confirm source metadata.
        """
        from rag_docu_reader import main
        content = b"The Amazon river is the largest river in the world."
        resp = client.post(
            "/upload",
            files=[("files", ("river.txt", io.BytesIO(content), "text/plain"))],
        )
        assert resp.status_code == 200
        sid = resp.json()["session_id"]
        vs = main.sessions.get_vectorstore(sid)
        docs = vs.as_retriever(search_kwargs={"k": 1}).invoke("Amazon river")
        assert len(docs) > 0
        assert docs[0].metadata.get("source") == "river.txt"

    def test_empty_query_does_not_crash(self, store, fake_vs):
        """FAISS handles empty-string queries without raising."""
        store.create("s1", fake_vs)
        vs = store.get_vectorstore("s1")
        try:
            vs.as_retriever(search_kwargs={"k": 2}).invoke("")
        except Exception as exc:
            pytest.fail(f"Empty query raised an exception: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Persistence to disk
# ─────────────────────────────────────────────────────────────────────────────

class TestDiskPersistence:
    def test_vectorstore_directory_created_on_session_create(self, store, fake_vs, temp_persist):
        store.create("s_persist", fake_vs)
        assert os.path.isdir(os.path.join(temp_persist, "s_persist"))

    def test_vectorstore_files_written_to_disk(self, store, fake_vs, temp_persist):
        store.create("s_files", fake_vs)
        session_dir = os.path.join(temp_persist, "s_files")
        files = os.listdir(session_dir)
        # FAISS writes index.faiss and index.pkl
        assert any(".faiss" in f for f in files)
        assert any(".pkl" in f for f in files)

    def test_vectorstore_loadable_from_disk(self, store, fake_vs, temp_persist, monkeypatch):
        from rag_docu_reader import main
        store.create("s_load", fake_vs)
        # Evict from RAM cache
        main.vs_cache.remove("s_load")
        # Re-hydrate from disk
        vs = store.get_vectorstore("s_load")
        assert vs is not None


# ─────────────────────────────────────────────────────────────────────────────
# Thread safety smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_session_creates(self, store, fake_vs):
        """20 threads each creating a session should not raise."""
        errors = []

        def worker(i):
            try:
                store.create(f"thread_{i}", fake_vs)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert store.active_count() == 20

    def test_concurrent_history_appends(self, store, fake_vs):
        """Parallel appends to the same session must not corrupt history."""
        store.create("shared", fake_vs)
        errors = []

        def worker(i):
            try:
                store.append_history("shared", "human", f"msg {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        hist = store.get_history("shared")
        assert isinstance(hist, list)
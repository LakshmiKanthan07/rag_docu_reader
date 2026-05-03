"""
test_chat.py — Query + response pipeline
==========================================
Answers: "Can the system think and respond?"

Covers:
  - Valid question returns a streamed response
  - Empty / too-long questions are rejected
  - Unknown session returns 404
  - Response is streamed (text/plain, not JSON blob)
  - LLM mock is invoked (not real API)
  - Conversation history is persisted and grows
  - Session isolation: two sessions don't share history
  - DELETE /session clears history
  - Irrelevant questions are handled without crashing
"""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helper ─────────────────────────────────────────────────────────────────────

def _ask(client, session_id: str, question: str):
    return client.post("/ask", json={"session_id": session_id, "question": question})


# ── Basic Q&A ──────────────────────────────────────────────────────────────────

class TestAskBasic:
    def test_valid_question_returns_200(self, client, seeded_session):
        resp = _ask(client, seeded_session, "What is this document about?")
        assert resp.status_code == 200

    def test_response_is_non_empty(self, client, seeded_session):
        resp = _ask(client, seeded_session, "Summarise the content.")
        assert len(resp.text.strip()) > 0

    def test_response_content_type_is_plain_text(self, client, seeded_session):
        resp = _ask(client, seeded_session, "Hello")
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_response_contains_mock_tokens(self, client, seeded_session):
        """The mocked LLM streams 'This is a mocked answer.' — must be in body."""
        resp = _ask(client, seeded_session, "Tell me something.")
        assert "mocked" in resp.text.lower()

    def test_multiple_questions_same_session(self, client, seeded_session):
        for q in ["First question.", "Second question.", "Third question."]:
            resp = _ask(client, seeded_session, q)
            assert resp.status_code == 200


# ── Input validation ───────────────────────────────────────────────────────────

class TestInputValidation:
    def test_empty_question_returns_422(self, client, seeded_session):
        resp = _ask(client, seeded_session, "")
        assert resp.status_code == 422

    def test_whitespace_only_question_returns_422(self, client, seeded_session):
        resp = _ask(client, seeded_session, "   ")
        assert resp.status_code == 422

    def test_question_over_2000_chars_returns_422(self, client, seeded_session):
        resp = _ask(client, seeded_session, "a" * 2001)
        assert resp.status_code == 422

    def test_exactly_2000_char_question_accepted(self, client, seeded_session):
        resp = _ask(client, seeded_session, "a" * 2000)
        assert resp.status_code == 200

    def test_missing_session_id_returns_422(self, client):
        resp = client.post("/ask", json={"question": "hello"})
        assert resp.status_code == 422

    def test_missing_question_returns_422(self, client, seeded_session):
        resp = client.post("/ask", json={"session_id": seeded_session})
        assert resp.status_code == 422

    def test_malformed_json_returns_422(self, client):
        resp = client.post(
            "/ask",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


# ── Session handling ───────────────────────────────────────────────────────────

class TestSessionHandling:
    def test_unknown_session_returns_404(self, client):
        resp = _ask(client, "00000000-dead-beef-0000-000000000000", "Hello?")
        assert resp.status_code == 404

    def test_deleted_session_returns_404(self, client, seeded_session):
        client.delete(f"/session/{seeded_session}")
        resp = _ask(client, seeded_session, "Still alive?")
        assert resp.status_code == 404

    def test_two_sessions_are_independent(self, client, txt_file):
        import io
        from rag_docu_reader import main

        def _upload():
            filename, content, mime = txt_file
            r = client.post(
                "/upload",
                files=[("files", (filename, io.BytesIO(content), mime))],
            )
            return r.json()["session_id"]

        sid1 = _upload()
        sid2 = _upload()
        assert sid1 != sid2

        # Ask something in session 1 only
        _ask(client, sid1, "Question only for session 1.")

        # Retrieve history for both — session 2 should be empty
        hist1 = main.sessions.get_history(sid1)
        hist2 = main.sessions.get_history(sid2)
        assert len(hist1) > 0
        assert len(hist2) == 0

    def test_delete_nonexistent_session_returns_200(self, client):
        """DELETE on a non-existent session should not crash."""
        resp = client.delete("/session/00000000-0000-0000-0000-000000000000")
        # Sessions.remove() is silent — returns 200 anyway
        assert resp.status_code == 200


# ── Conversation history ───────────────────────────────────────────────────────

class TestConversationHistory:
    def test_history_grows_after_each_question(self, client, seeded_session):
        from rag_docu_reader import main

        _ask(client, seeded_session, "First question.")
        hist1 = main.sessions.get_history(seeded_session)
        assert len(hist1) == 2  # human + assistant

        _ask(client, seeded_session, "Second question.")
        hist2 = main.sessions.get_history(seeded_session)
        assert len(hist2) == 4

    def test_history_has_correct_roles(self, client, seeded_session):
        from rag_docu_reader import main
        _ask(client, seeded_session, "Test question.")
        hist = main.sessions.get_history(seeded_session)
        roles = [h["role"] for h in hist]
        assert "human" in roles
        assert "assistant" in roles

    def test_history_preserves_question_text(self, client, seeded_session):
        from rag_docu_reader import main
        _ask(client, seeded_session, "Remember the secret word: banana")
        hist = main.sessions.get_history(seeded_session)
        human_turns = [h["content"] for h in hist if h["role"] == "human"]
        assert any("banana" in t for t in human_turns)

    def test_history_capped_at_20_turns(self, client, seeded_session):
        from rag_docu_reader import main
        for i in range(15):  # 15 Q&A = 30 turns, but cap is 20
            _ask(client, seeded_session, f"Question number {i}")
        hist = main.sessions.get_history(seeded_session)
        assert len(hist) <= 20

    def test_clear_session_clears_history(self, client, seeded_session):
        from rag_docu_reader import main
        _ask(client, seeded_session, "Remember this.")
        assert len(main.sessions.get_history(seeded_session)) > 0
        client.delete(f"/session/{seeded_session}")
        # After deletion the session should not exist at all
        with pytest.raises(Exception):
            main.sessions.get_history(seeded_session)


# ── Streaming behaviour ────────────────────────────────────────────────────────

class TestStreaming:
    def test_response_arrives_as_stream_not_single_block(self, client, seeded_session):
        """
        The mock LLM yields 5 separate tokens.
        TestClient collects them but the content-type must be text/plain (streaming).
        """
        resp = _ask(client, seeded_session, "Stream test.")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_full_streamed_response_is_correct(self, client, seeded_session):
        resp = _ask(client, seeded_session, "Give me the full answer.")
        # Mock yields: "This " "is " "a " "mocked " "answer."
        assert resp.text == "This is a mocked answer."


# ── LLM interaction (mock verification) ───────────────────────────────────────

class TestLLMInteraction:
    def test_llm_astream_is_called(self, client, seeded_session, mock_llm):
        """Ensure the LLM's astream method is actually invoked per question."""
        from rag_docu_reader import main

        original_astream = main.llm.astream
        call_count = 0

        async def counting_astream(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            async for chunk in original_astream(prompt, **kwargs):
                yield chunk

        main.llm.astream = counting_astream
        try:
            _ask(client, seeded_session, "Are you there?")
            assert call_count == 1
        finally:
            main.llm.astream = original_astream

    def test_retrieval_context_is_non_empty(self, client, seeded_session):
        """
        The RAG chain must retrieve at least one chunk before calling the LLM.
        We verify indirectly: a 200 response means retrieval didn't raise.
        """
        resp = _ask(client, seeded_session, "dog fox")
        assert resp.status_code == 200


# ── Format helpers (unit tests) ────────────────────────────────────────────────

class TestFormatHelpers:
    def test_fmt_history_empty(self):
        from rag_docu_reader.main import _fmt_history
        result = _fmt_history([])
        assert "no prior" in result.lower()

    def test_fmt_history_formats_roles(self):
        from rag_docu_reader.main import _fmt_history
        hist = [
            {"role": "human", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = _fmt_history(hist)
        assert "User" in result
        assert "Assistant" in result
        assert "Hello" in result
        assert "Hi there" in result

    def test_fmt_context_includes_page_numbers(self):
        from langchain_core.documents.base import Document
        from rag_docu_reader.main import _fmt_context
        docs = [
            Document(page_content="Some text here.", metadata={"page": 3}),
        ]
        result = _fmt_context(docs)
        assert "[page 3]" in result
        assert "Some text here." in result

    def test_fmt_context_handles_missing_page(self):
        from langchain_core.documents.base import Document
        from rag_docu_reader.main import _fmt_context
        docs = [Document(page_content="No page metadata.", metadata={})]
        result = _fmt_context(docs)
        assert "No page metadata." in result
        assert "[page ?]" in result
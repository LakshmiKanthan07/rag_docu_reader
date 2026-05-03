"""
test_basic.py — Sanity + environment checks
============================================
Answers: "Is the system alive and correctly configured?"

Covers:
  - App can be imported without crashing
  - Health endpoint is reachable and well-formed
  - Metrics endpoint returns expected keys
  - CORS headers are present
  - 404 on unknown routes
  - Configuration constants have sane defaults
"""
from rag_docu_reader import main
import pytest


class TestAppImport:
    """The module and its core objects must be importable and non-None."""

    def test_app_object_exists(self):
        assert main.app is not None

    def test_sessions_object_exists(self):
        assert main.sessions is not None

    def test_llm_object_exists(self):
        assert main.llm is not None

    def test_embeddings_object_exists(self):
        assert main.embeddings is not None

    def test_rag_prompt_exists(self):
        assert main.RAG_PROMPT is not None

    def test_allowed_extensions_non_empty(self):
        assert len(main.ALLOWED_EXTENSIONS) > 0

    def test_loader_map_covers_allowed_extensions(self):
        """Every allowed extension must have a loader registered."""
        for ext in main.ALLOWED_EXTENSIONS:
            assert ext in main.LOADER_MAP, f"No loader for allowed extension: {ext}"


class TestConfigDefaults:
    """Environment-driven config must fall back to sensible defaults."""

    def test_chunk_size_positive(self):
        assert main.CHUNK_SIZE > 0

    def test_chunk_overlap_less_than_chunk_size(self):
        assert main.CHUNK_OVERLAP < main.CHUNK_SIZE

    def test_top_k_positive(self):
        assert main.TOP_K > 0

    def test_session_ttl_positive(self):
        assert main.SESSION_TTL_HOURS > 0

    def test_max_file_size_positive(self):
        assert main.MAX_FILE_SIZE > 0

    def test_vs_cache_size_positive(self):
        assert main.VS_CACHE_SIZE > 0


class TestHealthEndpoint:
    """/health must be reachable without auth and return the correct shape."""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_json_has_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_json_has_timestamp(self, client):
        data = client.get("/health").json()
        assert "timestamp" in data
        # should be ISO-8601 (contains 'T')
        assert "T" in data["timestamp"]

    def test_health_json_has_sessions_count(self, client):
        data = client.get("/health").json()
        assert "sessions" in data
        assert isinstance(data["sessions"], int)

    def test_health_is_fast(self, client):
        """Health check must not call the LLM — should be near-instant."""
        import time
        start = time.monotonic()
        client.get("/health")
        assert time.monotonic() - start < 2.0


class TestMetricsEndpoint:
    """/metrics must expose the expected counters."""

    def test_metrics_returns_200(self, client):
        assert client.get("/metrics").status_code == 200

    def test_metrics_has_required_keys(self, client):
        data = client.get("/metrics").json()
        for key in ("uploads_total", "uploads_failed", "questions_total", "sessions_active"):
            assert key in data, f"Missing metric key: {key}"

    def test_metrics_values_are_non_negative_ints(self, client):
        data = client.get("/metrics").json()
        for key in ("uploads_total", "uploads_failed", "questions_total", "sessions_active"):
            assert isinstance(data[key], int)
            assert data[key] >= 0


class TestRouting:
    """Unknown routes must return 404, not 500."""

    def test_unknown_route_returns_404(self, client):
        assert client.get("/nonexistent").status_code == 404

    def test_unknown_post_route_returns_404(self, client):
        assert client.post("/nonexistent", json={}).status_code == 404


class TestCORS:
    """CORS middleware must inject the allow-origin header for configured origins."""

    def test_cors_header_present_for_allowed_origin(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:8000"},
        )
        assert "access-control-allow-origin" in resp.headers

    def test_options_preflight(self, client):
        resp = client.options(
            "/upload",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
            },
        )
        # preflight should not return 500
        assert resp.status_code in (200, 204)


class TestAuthMiddleware:
    """When API_KEY is set, requests without the correct header must be rejected."""

    def test_upload_without_key_returns_401(self, authed_client):
        resp = authed_client.post("/upload", files=[("files", ("a.txt", b"hi", "text/plain"))])
        assert resp.status_code == 401

    def test_upload_with_wrong_key_returns_401(self, authed_client):
        resp = authed_client.post(
            "/upload",
            files=[("files", ("a.txt", b"hi", "text/plain"))],
            headers={"x-api-key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_upload_with_correct_key_passes_auth(self, authed_client):
        resp = authed_client.post(
            "/upload",
            files=[("files", ("a.txt", b"The quick brown fox.", "text/plain"))],
            headers={"x-api-key": "secret-test-key"},
        )
        # 200 or 422 are fine — auth passed, pipeline ran
        assert resp.status_code in (200, 422)
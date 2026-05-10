# Graph Report - .  (2026-05-07)

## Corpus Check
- 34 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 339 nodes · 482 edges · 17 communities
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.63)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Core Backend & Vector Cache|Core Backend & Vector Cache]]
- [[_COMMUNITY_Document Upload Verification|Document Upload Verification]]
- [[_COMMUNITY_Chat Interaction Testing|Chat Interaction Testing]]
- [[_COMMUNITY_Frontend UI & Components|Frontend UI & Components]]
- [[_COMMUNITY_System Configuration & Middleware Tests|System Configuration & Middleware Tests]]
- [[_COMMUNITY_Data Models & Auth API|Data Models & Auth API]]
- [[_COMMUNITY_Shared Test Fixtures|Shared Test Fixtures]]
- [[_COMMUNITY_Vectorstore Retrieval & Persistence|Vectorstore Retrieval & Persistence]]
- [[_COMMUNITY_Session Management Testing|Session Management Testing]]
- [[_COMMUNITY_Document Parsing & Formatting|Document Parsing & Formatting]]
- [[_COMMUNITY_Application Setup Tests|Application Setup Tests]]
- [[_COMMUNITY_Cloud Storage & Async Tasks|Cloud Storage & Async Tasks]]

## God Nodes (most connected - your core abstractions)
1. `_upload()` - 31 edges
2. `_ask()` - 22 edges
3. `SessionStore` - 21 edges
4. `LRUVectorstoreCache` - 18 edges
5. `TestSessionStore` - 15 edges
6. `Document` - 13 edges
7. `User` - 12 edges
8. `TestLRUVectorstoreCache` - 10 edges
9. `Chat` - 9 edges
10. `loadDocuments()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `LRUVectorstoreCache` --uses--> `TestSessionStore`  [INFERRED]
  rag_docu_reader/main.py → test/test_vectorstore.py
- `LRUVectorstoreCache` --uses--> `TestRetrieval`  [INFERRED]
  rag_docu_reader/main.py → test/test_vectorstore.py
- `LRUVectorstoreCache` --uses--> `TestDiskPersistence`  [INFERRED]
  rag_docu_reader/main.py → test/test_vectorstore.py
- `LRUVectorstoreCache` --uses--> `TestConcurrency`  [INFERRED]
  rag_docu_reader/main.py → test/test_vectorstore.py
- `SessionStore` --uses--> `TestSessionStore`  [INFERRED]
  rag_docu_reader/main.py → test/test_vectorstore.py

## Communities (17 total, 0 thin omitted)

### Community 0 - "Core Backend & Vector Cache"
Cohesion: 0.07
Nodes (22): init(), loadDocuments(), cleanup_file(), delete_session(), health(), JSONFormatter, lifespan(), LRUVectorstoreCache (+14 more)

### Community 1 - "Document Upload Verification"
Cohesion: 0.07
Nodes (15): test_upload.py — File ingestion pipeline ======================================, Valid + invalid: session created from valid file; invalid is skipped., A freshly created session must respond to /ask without 404., A file with 10× the chunk size should be split., Real docx/xlsx bytes are generated with python-docx / openpyxl.     If those ar, Helper: POST /upload with one or more (filename, bytes, mime) tuples., TestChunkMetadata, TestDocxXlsxLoaders (+7 more)

### Community 2 - "Chat Interaction Testing"
Cohesion: 0.08
Nodes (13): _ask(), test_chat.py — Query + response pipeline ======================================, DELETE on a non-existent session should not crash., The mock LLM yields 5 separate tokens.         TestClient collects them but the, Ensure the LLM's astream method is actually invoked per question., The RAG chain must retrieve at least one chunk before calling the LLM., The mocked LLM streams 'This is a mocked answer.' — must be in body., TestAskBasic (+5 more)

### Community 3 - "Frontend UI & Components"
Cohesion: 0.07
Nodes (33): aiMessageEl, apiCall(), appContainer, authError, authForm, authModal, authSubmitBtn, chatForm (+25 more)

### Community 4 - "System Configuration & Middleware Tests"
Cohesion: 0.06
Nodes (14): test_basic.py — Sanity + environment checks ===================================, Unknown routes must return 404, not 500., CORS middleware must inject the allow-origin header for configured origins., When API_KEY is set, requests without the correct header must be rejected., Environment-driven config must fall back to sensible defaults., /health must be reachable without auth and return the correct shape., Health check must not call the LLM — should be near-instant., /metrics must expose the expected counters. (+6 more)

### Community 5 - "Data Models & Auth API"
Cohesion: 0.12
Nodes (18): Base, BaseModel, BaseSettings, Config, Settings, Chat, Message, User (+10 more)

### Community 6 - "Shared Test Fixtures"
Cohesion: 0.08
Nodes (19): authed_client(), cleanup_persist_dir(), client(), _fake_embed_query(), large_file(), mock_embeddings(), mock_llm(), conftest.py — Shared test environment for DocTalk API ========================= (+11 more)

### Community 7 - "Vectorstore Retrieval & Persistence"
Cohesion: 0.08
Nodes (14): fake_vs(), test_vectorstore.py — Retrieval engine ========================================, Upload a txt file, retrieve the vectorstore, confirm source metadata., FAISS handles empty-string queries without raising., 20 threads each creating a session should not raise., A real FAISS vectorstore built with FakeEmbeddings (no Ollama needed)., Parallel appends to the same session must not corrupt history., Isolated persist directory for SessionStore tests. (+6 more)

### Community 8 - "Session Management Testing"
Cohesion: 0.12
Nodes (4): Should not raise — silently ignored., Evict from LRU cache; session must reload from disk transparently., Sessions past TTL must be rejected., TestSessionStore

### Community 9 - "Document Parsing & Formatting"
Cohesion: 0.2
Nodes (6): Document, load_docx_file(), load_xlsx_file(), _make_fake_vectorstore(), Return a real in-memory FAISS store seeded with trivial content., TestFormatHelpers

### Community 10 - "Application Setup Tests"
Cohesion: 0.2
Nodes (3): The module and its core objects must be importable and non-None., Every allowed extension must have a loader registered., TestAppImport

### Community 11 - "Cloud Storage & Async Tasks"
Cohesion: 0.5
Nodes (3): get_s3_client(), upload_file_to_s3(), process_document()

## Knowledge Gaps
- **74 isolated node(s):** `Thread-safe in-memory LRU cache for FAISS vectorstores.     Prevents repeated d`, `Registry of active sessions.     Vectorstores are persisted to disk; hot sessio`, `Append a turn to history only if the session still exists.         Silently no-`, `authModal`, `appContainer` (+69 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Document` connect `Document Parsing & Formatting` to `Core Backend & Vector Cache`, `Session Management Testing`, `Data Models & Auth API`, `Vectorstore Retrieval & Persistence`?**
  _High betweenness centrality (0.430) - this node is a cross-community bridge._
- **Why does `TestFormatHelpers` connect `Document Parsing & Formatting` to `Chat Interaction Testing`?**
  _High betweenness centrality (0.304) - this node is a cross-community bridge._
- **Why does `_upload()` connect `Document Upload Verification` to `Chat Interaction Testing`?**
  _High betweenness centrality (0.205) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `SessionStore` (e.g. with `TestLRUVectorstoreCache` and `TestSessionStore`) actually correct?**
  _`SessionStore` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `LRUVectorstoreCache` (e.g. with `TestLRUVectorstoreCache` and `TestSessionStore`) actually correct?**
  _`LRUVectorstoreCache` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TestSessionStore` (e.g. with `LRUVectorstoreCache` and `SessionStore`) actually correct?**
  _`TestSessionStore` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Thread-safe in-memory LRU cache for FAISS vectorstores.     Prevents repeated d`, `Registry of active sessions.     Vectorstores are persisted to disk; hot sessio`, `Append a turn to history only if the session still exists.         Silently no-` to the rest of the system?**
  _74 weakly-connected nodes found - possible documentation gaps or missing edges._
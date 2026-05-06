import chromadb
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Use a free lightweight embedding model, configurable via .env
embeddings = HuggingFaceEmbeddings(model_name=settings.EMBED_MODEL)

try:
    # Try connecting to Chroma Server (Docker)
    chroma_client = chromadb.HttpClient(host="chroma", port=8000)
    chroma_client.heartbeat()
    logger.info("Connected to Chroma HTTP Client")
except Exception as e:
    logger.warning(f"Could not connect to Chroma server, falling back to local persistent Chroma: {e}")
    chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

def get_vectorstore(collection_name="documents"):
    return Chroma(
        client=chroma_client,
        collection_name=collection_name,
        embedding_function=embeddings,
    )

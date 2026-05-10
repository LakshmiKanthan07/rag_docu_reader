import os
from langchain_postgres import PGVector
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Serverless embeddings via HuggingFace Inference API
# This removes the need to run heavy models on your CPU/GPU
hf_token = os.getenv("HF_TOKEN")
if not hf_token:
    logger.warning("HF_TOKEN not found in environment. Serverless embeddings may fail.")

embeddings = HuggingFaceInferenceAPIEmbeddings(
    api_key=hf_token, 
    model_name=settings.EMBED_MODEL # defaults to "all-MiniLM-L6-v2"
)

# Supabase (Postgres) connection string for PGVector
# Note: langchain-postgres uses psycopg v3
connection_string = settings.DATABASE_URL

def get_vectorstore(collection_name="documents"):
    """
    Returns a PGVector instance connected to Supabase.
    This replaces the local ChromaDB implementation.
    """
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=connection_string,
        use_jsonb=True,
    )

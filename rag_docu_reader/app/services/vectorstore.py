import os
import logging
from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

def get_embeddings():
    # Using the more robust HuggingFaceEndpointEmbeddings
    # This automatically handles the HuggingFace Inference API
    return HuggingFaceEndpointEmbeddings(
        huggingfacehub_api_token=settings.HF_TOKEN,
        model=f"sentence-transformers/{settings.EMBED_MODEL}" if "/" not in settings.EMBED_MODEL else settings.EMBED_MODEL
    )

def get_vectorstore(collection_name: str = "doctalk_collection"):
    # Ensure the connection string uses the postgresql driver (Supabase provides postgres://)
    connection_string = settings.DATABASE_URL.replace("postgres://", "postgresql://")
    
    # We create the embeddings instance on each call to avoid stale state in long-running processes
    embeddings = get_embeddings()
    
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=connection_string,
        use_jsonb=True,
    )

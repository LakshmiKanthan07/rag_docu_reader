import os
import tempfile
from app.core.celery_app import celery_app
from langchain_community.document_loaders import PyPDFLoader, TextLoader, CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.services.vectorstore import get_vectorstore
from app.services.storage import get_s3_client
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

@celery_app.task
def process_document(document_id: str, s3_url: str, filename: str, chat_id: str, user_id: str):
    logger.info(f"Processing document {document_id}")
    
    # 1. Download file from S3 to temp file
    s3 = get_s3_client()
    ext = os.path.splitext(filename)[1].lower()
    
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        s3_key = s3_url.split(f"/{settings.S3_BUCKET_NAME}/")[-1]
        s3.download_fileobj(settings.S3_BUCKET_NAME, s3_key, tmp)
        tmp_path = tmp.name
        
    try:
        # 2. Extract Text
        if ext == '.pdf':
            loader = PyPDFLoader(tmp_path)
        elif ext == '.csv':
            loader = CSVLoader(tmp_path)
        else:
            loader = TextLoader(tmp_path)
            
        docs = loader.load()
        
        # 3. Chunk
        splitter = RecursiveCharacterTextSplitter(chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
        chunks = splitter.split_documents(docs)
        
        # 4. Add Metadata
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                "document_id": document_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "filename": filename,
                "page": chunk.metadata.get("page", i + 1)
            })
            
        # 5. Insert to Chroma
        vectorstore = get_vectorstore()
        vectorstore.add_documents(chunks)
        
        logger.info(f"Successfully processed and embedded {len(chunks)} chunks for {document_id}")
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}")
        raise
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

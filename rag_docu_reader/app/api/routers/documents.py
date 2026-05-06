import uuid
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime
from app.db.database import get_db
from app.models.user import User
from app.models.chat import Chat
from app.models.document import Document
from app.api.deps import get_current_user
from app.services.storage import upload_file_to_s3

router = APIRouter()

class DocumentResponse(BaseModel):
    id: str
    filename: str
    size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True

@router.get("/chats/{chat_id}/documents", response_model=List[DocumentResponse])
async def get_chat_documents(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify chat belongs to user
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    return db.query(Document).filter(Document.chat_id == chat_id).order_by(Document.created_at.desc()).all()

@router.post("/chats/{chat_id}/upload")
async def upload_document(
    chat_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify chat belongs to user
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    ext = os.path.splitext(file.filename)[1].lower()
    unique_filename = f"{chat_id}/{uuid.uuid4()}{ext}"
    
    # Calculate size
    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)
    
    # Upload to S3
    try:
        s3_url = upload_file_to_s3(file.file, unique_filename, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to storage: {str(e)}")
        
    doc = Document(
        filename=file.filename,
        s3_url=s3_url,
        size_bytes=size_bytes,
        chat_id=chat_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    from app.services.tasks import process_document
    
    process_document.delay(
        document_id=doc.id,
        s3_url=s3_url,
        filename=doc.filename,
        chat_id=chat_id,
        user_id=current_user.id
    )
    
    return {"message": "Document uploaded successfully", "document": {"id": doc.id, "filename": doc.filename, "s3_url": s3_url}}

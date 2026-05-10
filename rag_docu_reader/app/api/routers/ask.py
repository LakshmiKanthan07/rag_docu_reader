from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.db.database import get_db
from app.models.user import User
from app.models.chat import Chat
from app.models.message import Message
from app.api.deps import get_current_user
from app.services.vectorstore import get_vectorstore
from app.core.config import settings

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class AskRequest(BaseModel):
    question: str

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.3,
    max_tokens=1024,
)

RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are a precise document assistant. Answer questions strictly from the context below.

Rules:
- Use ONLY the provided context. No outside knowledge.
- If the answer is absent from the context, say: "I don't know based on the provided document."
- Be concise and direct. Skip filler like "Based on the context...".
- After your answer, list the sources you used on a new line in the format:
  Sources: [page X], [page Y]  (use the page numbers shown in the context blocks)
  If no page numbers are available, omit the Sources line.
- Never guess, infer beyond the text, or hallucinate.don't try to use more emojis keep it minimal 

--- DOCUMENT CONTEXT ---
{context}
--- END CONTEXT ---

Conversation history:
{history}

User: {question}
Assistant:"""
)

def _fmt_history(history: List[Message]) -> str:
    if not history:
        return "(no prior conversation)"
    lines = []
    for h in history:
        speaker = "User" if h.role == "human" else "Assistant"
        lines.append(f"{speaker}: {h.content}")
    return "\n".join(lines)

def _fmt_context(docs) -> str:
    parts = []
    for doc in docs:
        page = doc.metadata.get("page", "?")
        parts.append(f"[page {page}]\n{doc.page_content}")
    return "\n\n".join(parts)

@router.post("/chats/{chat_id}/ask")
async def ask_question(
    chat_id: str,
    req: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Verify Chat
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 2. Retrieve history
    history = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at.asc()).limit(20).all()

    # 3. Retrieve context
    try:
        vectorstore = get_vectorstore()
        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": settings.TOP_K, 
                "filter": {"chat_id": chat_id} 
            }
        )
        docs = await asyncio.to_thread(retriever.invoke, req.question)
        context = _fmt_context(docs)
    except Exception as e:
        logger.exception("Retrieval error")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

    # 4. Prompt construction
    final_prompt = RAG_PROMPT.invoke({
        "context": context,
        "history": _fmt_history(history),
        "question": req.question,
    })

    # 5. Streaming Generator
    async def stream_tokens():
        collected = []
        try:
            async for chunk in llm.astream(final_prompt):
                token = chunk.content
                if token:
                    collected.append(token)
                    yield token
        except Exception as exc:
            logger.exception("Streaming error")
            yield f"\n[ERROR: {exc}]"
        finally:
            full_answer = "".join(collected)
            
            # Save messages to DB
            human_msg = Message(role="human", content=req.question, chat_id=chat_id)
            ai_msg = Message(role="assistant", content=full_answer, chat_id=chat_id)
            
            db.add(human_msg)
            db.add(ai_msg)
            db.commit()

    return StreamingResponse(stream_tokens(), media_type="text/plain")

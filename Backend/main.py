import os
import json
import shutil
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import ChatMessage, get_db
from pipeline import (
    index_pdf,
    rag_query,
    list_indexed_documents,
    get_chroma_client,
    filename_to_collection_name,
)

# ── Keep-alive ping to prevent Render cold start ───────────────────────────────

async def keep_alive():
    """
    Pings the server every 10 minutes to prevent Render free tier
    from spinning down due to inactivity.
    Without this, first request after 15min idle takes 30-60 seconds.
    """
    await asyncio.sleep(60)  # wait for server to fully start first
    while True:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.get(
                    "https://rag-chat-thku.onrender.com/",
                    timeout=10
                )
                print("Keep-alive ping sent successfully.")
        except Exception as e:
            print(f"Keep-alive ping failed: {e}")
        await asyncio.sleep(600)  # ping every 10 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs keep-alive task when server starts."""
    asyncio.create_task(keep_alive())
    yield  # server runs here
    # cleanup on shutdown (nothing needed)


# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAG API",
    version="1.0.0",
    lifespan=lifespan  # attach keep-alive
)

# CORS — allows React frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Absolute path for uploads folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve uploaded PDFs as static files
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ── Pydantic models ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    collection_name: str

class SourceChunk(BaseModel):
    text: str
    page: int
    source: str

class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]

class DocumentInfo(BaseModel):
    collection_name: str
    chunk_count: int

class MessageIn(BaseModel):
    session_id: str
    collection_name: str
    role: str
    content: str
    sources: list = []

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Health check — confirms API is running."""
    return {"status": "RAG API is running"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accepts PDF upload, saves to disk, indexes into ChromaDB.
    Returns collection_name for frontend to use in queries.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    collection = index_pdf(file_path)

    return {
        "message": f"'{file.filename}' uploaded and indexed successfully.",
        "collection_name": filename_to_collection_name(file_path),
        "chunk_count": collection.count(),
    }


@app.post("/query", response_model=QueryResponse)
def query_document(request: QueryRequest):
    """
    Runs HyDE + multi-query RAG pipeline.
    Returns grounded answer with page citations.
    """
    try:
        collection = get_chroma_client().get_collection(
            name=request.collection_name
        )
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{request.collection_name}' not found. Upload the document first."
        )

    result = rag_query(request.question, collection)

    return QueryResponse(
        answer=result["answer"],
        sources=[SourceChunk(**s) for s in result["sources"]],
    )


@app.get("/documents", response_model=list[DocumentInfo])
def get_documents():
    """Returns list of all indexed documents."""
    docs = list_indexed_documents()
    return [DocumentInfo(**d) for d in docs]


@app.delete("/documents/{collection_name}")
def delete_document(collection_name: str):
    """Deletes a document collection from ChromaDB."""
    try:
        get_chroma_client().delete_collection(name=collection_name)
    except Exception:
        raise HTTPException(status_code=404, detail="Collection not found.")
    return {"message": f"'{collection_name}' deleted successfully."}


@app.get("/files/list")
def list_uploads():
    """Returns list of uploaded PDF filenames for download feature."""
    if not os.path.exists(UPLOAD_DIR):
        return []
    files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".pdf")]
    return files


# ── Chat History Routes ────────────────────────────────────────────────────────

@app.post("/history")
def save_message(msg: MessageIn, db: Session = Depends(get_db)):
    """Saves a chat message to SQLite."""
    db_msg = ChatMessage(
        session_id=msg.session_id,
        collection_name=msg.collection_name,
        role=msg.role,
        content=msg.content,
        sources=json.dumps(msg.sources),
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    return {"id": db_msg.id, "message": "Saved"}


@app.get("/history/{session_id}/{collection_name}")
def get_history(
    session_id: str,
    collection_name: str,
    db: Session = Depends(get_db)
):
    """Returns full chat history for a session + document."""
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.collection_name == collection_name,
        )
        .order_by(ChatMessage.timestamp)
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else [],
            "timestamp": m.timestamp.isoformat(),
        }
        for m in messages
    ]


@app.delete("/history/{session_id}/{collection_name}")
def clear_history(
    session_id: str,
    collection_name: str,
    db: Session = Depends(get_db)
):
    """Clears chat history for a session + document."""
    db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id,
        ChatMessage.collection_name == collection_name,
    ).delete()
    db.commit()
    return {"message": "History cleared"}


# ── Run locally ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
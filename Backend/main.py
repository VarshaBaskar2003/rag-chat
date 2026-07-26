import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pipeline import index_pdf, rag_query, list_indexed_documents, chroma_client, filename_to_collection_name
import json
from sqlalchemy.orm import Session
from fastapi import Depends
from database import ChatMessage, get_db
from fastapi.staticfiles import StaticFiles
# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="RAG API", version="1.0.0")


# CORS — allows your React frontend (running on port 5173) to call this API
# Without this, the browser will block all requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Folder where uploaded PDFs are saved
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")    

# ── Request/Response models ───────────────────────────────────────────────────

# Pydantic models define the shape of JSON requests and responses
# FastAPI uses these for automatic validation and documentation

class QueryRequest(BaseModel):
    question: str          # the user's question
    collection_name: str   # which document to search in

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

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Health check — visit http://localhost:8000 to confirm API is running."""
    return {"status": "RAG API is running"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accepts a PDF file upload, saves it to disk, and indexes it into ChromaDB.
    Returns the collection_name the frontend needs to send with future queries.

    UploadFile = FastAPI's built-in file upload type
    File(...) = this field is required (the ... means required in Pydantic)
    """
    # Validate that the uploaded file is actually a PDF
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Save the uploaded file to the uploads/ folder
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)  # copyfileobj streams the file to disk efficiently

    # Index the PDF using our pipeline
    # This runs: extract → chunk → embed → store in ChromaDB
    collection = index_pdf(file_path)

    return {
        "message": f"'{file.filename}' uploaded and indexed successfully.",
        "collection_name": filename_to_collection_name(file_path),
        "chunk_count": collection.count(),
    }


@app.post("/query", response_model=QueryResponse)
def query_document(request: QueryRequest):
    """
    Accepts a question and collection_name, runs RAG, returns answer + sources.
    The frontend sends both the question and which document to search.
    """
    # Validate the collection exists
    try:
        collection = chroma_client.get_collection(name=request.collection_name)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{request.collection_name}' not found. Please upload the document first."
        )

    # Run the RAG pipeline
    result = rag_query(request.question, collection)

    return QueryResponse(
        answer=result["answer"],
        sources=[SourceChunk(**s) for s in result["sources"]],
    )


@app.get("/documents", response_model=list[DocumentInfo])
def get_documents():
    """
    Returns a list of all indexed documents.
    The frontend uses this to populate the document selector dropdown.
    """
    docs = list_indexed_documents()
    return [DocumentInfo(**d) for d in docs]


@app.delete("/documents/{collection_name}")
def delete_document(collection_name: str):
    """
    Deletes a document collection from ChromaDB.
    Also removes the uploaded PDF from disk.
    """
    try:
        chroma_client.delete_collection(name=collection_name)
    except Exception:
        raise HTTPException(status_code=404, detail="Collection not found.")

    return {"message": f"'{collection_name}' deleted successfully."}

# Change this route
@app.get("/files/list")  # was /uploads/list
def list_uploads():
    if not os.path.exists(UPLOAD_DIR):
        return []
    files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".pdf")]
    return files
# ── Chat History Routes ────────────────────────────────────────────────────────

class MessageIn(BaseModel):
    session_id: str
    collection_name: str
    role: str
    content: str
    sources: list = []

@app.post("/history")
def save_message(msg: MessageIn, db: Session = Depends(get_db)):
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
def get_history(session_id: str, collection_name: str, db: Session = Depends(get_db)):
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
def clear_history(session_id: str, collection_name: str, db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id,
        ChatMessage.collection_name == collection_name,
    ).delete()
    db.commit()
    return {"message": "History cleared"}


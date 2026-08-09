import os
import json
import fitz  # PyMuPDF
import chromadb
from groq import Groq
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

# ── Splitter (lightweight, safe to initialize at startup) ─────────────────────
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
)

# ── Lazy initialization — models load on first use, not at startup ────────────
# This lets FastAPI start and bind to port immediately
# Render's free tier kills apps that don't bind a port within 60 seconds

_embed_model = None
_chroma_client = None
_groq_client = None


def get_embed_model():
    """
    Load embedding model only when first needed.
    Using all-MiniLM-L2-v2 instead of L6 because:
    - L2 uses ~100MB RAM
    - L6 uses ~500MB RAM
    - Render free tier limit is 512MB
    - L2 is still accurate enough for RAG
    """
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        print("Loading embedding model...")
        _embed_model = SentenceTransformer("all-MiniLM-L2-v2")
        print("Embedding model loaded.")
    return _embed_model


def get_chroma_client():
    """Create ChromaDB client only when first needed."""
    global _chroma_client
    if _chroma_client is None:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        CHROMA_PATH = os.path.join(BASE_DIR, "chroma_data")
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        print("ChromaDB client initialized.")
    return _chroma_client


def get_groq_client():
    """Create Groq client only when first needed."""
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        print("Groq client initialized.")
    return _groq_client


# ── Helper: convert filename to valid ChromaDB collection name ─────────────────

def filename_to_collection_name(pdf_path: str) -> str:
    """
    Converts a filename to a valid ChromaDB collection name.
    ChromaDB collection names must be lowercase with only letters,
    numbers, and underscores.
    e.g. "My Document.pdf" → "my_document_pdf"
    """
    name = os.path.basename(pdf_path)   # get filename only, not full path
    name = name.replace(".", "_")        # dots to underscore
    name = name.replace(" ", "_")        # spaces to underscore
    name = name.replace("-", "_")        # hyphens to underscore
    name = name.lower()                  # lowercase
    return name


# ── Function 1: Extract text from PDF page by page ────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Opens a PDF and extracts text page by page.
    Returns: [{"page": 1, "text": "..."}, {"page": 2, "text": "..."}, ...]
    We store page numbers so we can cite sources later.
    """
    doc = fitz.open(pdf_path)
    pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        # Skip blank or image-only pages
        if len(text.strip()) > 50:
            pages.append({
                "page": page_num + 1,  # humans count from 1 not 0
                "text": text
            })

    doc.close()
    print(f"Extracted text from {len(pages)} pages.")
    return pages


# ── Function 2: Index a PDF into ChromaDB ─────────────────────────────────────

def index_pdf(pdf_path: str):
    """
    Full ingestion pipeline:
    PDF → extract text → chunk → embed → store in ChromaDB

    Each PDF gets its own persistent collection named after the file.
    If already indexed, skips re-processing to save time and memory.

    Returns the ChromaDB collection object.
    """
    collection_name = filename_to_collection_name(pdf_path)
    chroma = get_chroma_client()
    embed = get_embed_model()

    # Get or create collection for this specific PDF
    collection = chroma.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}  # cosine similarity not L2
    )

    # Skip if already indexed
    if collection.count() > 0:
        print(f"'{collection_name}' already indexed ({collection.count()} chunks). Skipping.")
        return collection

    # Step 1: Extract text
    pages = extract_text_from_pdf(pdf_path)

    # Step 2: Chunk each page
    all_chunks = []
    all_metadatas = []
    all_ids = []
    chunk_counter = 0

    for page_data in pages:
        page_chunks = splitter.split_text(page_data["text"])

        for chunk_text in page_chunks:
            # Skip very short chunks — usually noise
            if len(chunk_text.strip()) < 100:
                continue

            all_chunks.append(chunk_text)
            all_metadatas.append({
                "source": os.path.basename(pdf_path),
                "page": page_data["page"],
                "chunk_index": chunk_counter,
            })
            all_ids.append(f"chunk_{chunk_counter}")
            chunk_counter += 1

    print(f"Created {len(all_chunks)} chunks from {len(pages)} pages.")

    # Step 3: Embed all chunks in one batch
    print("Embedding chunks...")
    embeddings = embed.encode(all_chunks, show_progress_bar=True).tolist()

    # Step 4: Store in ChromaDB in batches of 100
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        collection.add(
            ids=all_ids[i:i+batch_size],
            embeddings=embeddings[i:i+batch_size],
            documents=all_chunks[i:i+batch_size],
            metadatas=all_metadatas[i:i+batch_size],
        )

    print(f"Indexed {collection.count()} chunks into ChromaDB.")
    return collection


# ── Function 3: Generate hypothetical answer (HyDE) ───────────────────────────

def generate_hypothetical_answer(question: str) -> str:
    """
    HyDE — Hypothetical Document Embeddings.

    Instead of embedding the raw question, we ask the LLM to generate
    a fake answer that WOULD appear in a document.
    That fake answer uses document-like vocabulary → better retrieval.

    Example:
      Question: "What are the key ideas?"
      Hypothetical: "The key ideas include attention mechanisms,
                     transformer architecture, multi-head attention..."
      → Matches real document chunks much better than "key ideas" alone
    """
    groq = get_groq_client()

    prompt = f"""You are an expert. Write a short detailed paragraph 
that would be a perfect answer to the following question, 
as if you were reading it from a technical document.
Do not say you don't know. Just write what a good answer would look like.
Keep it under 150 words.

Question: {question}

Hypothetical answer:"""

    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content


# ── Function 4: Rewrite query into multiple variants ──────────────────────────

def rewrite_query(question: str) -> list[str]:
    """
    Generates 3 different search queries from the original question.
    More query variants = higher chance of finding the right chunks.

    Returns: [original_question, variant1, variant2, variant3]
    """
    groq = get_groq_client()

    prompt = f"""Generate 3 different search queries to find relevant 
content in a document for this question. Make them specific and varied.
Return ONLY a JSON array of 3 strings, nothing else.
Example: ["query 1", "query 2", "query 3"]

Question: {question}"""

    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    try:
        queries = json.loads(response.choices[0].message.content)
        return [question] + queries  # original + 3 rewrites
    except:
        return [question]  # fallback if JSON parsing fails


# ── Function 5: Full RAG query with HyDE + multi-query ────────────────────────

def rag_query(question: str, collection, n_chunks: int = 5) -> dict:
    """
    Complete RAG query pipeline:
    1. Generate hypothetical answer (HyDE)
    2. Rewrite query into 3 variants
    3. Search ChromaDB with all variants
    4. Deduplicate and merge results
    5. Build prompt with retrieved context
    6. Generate grounded answer with Groq LLM
    7. Return answer + source citations

    Returns: {"answer": str, "sources": [{"text", "page", "source"}]}
    """
    embed = get_embed_model()
    groq = get_groq_client()

    # Step 1: HyDE — generate hypothetical answer
    hypothetical = generate_hypothetical_answer(question)
    print(f"HyDE answer preview: {hypothetical[:80]}...")

    # Step 2: Multi-query rewriting
    queries = rewrite_query(question)
    print(f"Search queries: {queries}")

    # Step 3: Search with HyDE answer + all query variants
    all_search_texts = [hypothetical] + queries

    seen_ids = set()
    all_chunks = []
    all_metas = []

    for search_text in all_search_texts:
        query_vector = embed.encode([search_text]).tolist()
        results = collection.query(
            query_embeddings=query_vector,
            n_results=3,  # top 3 per query
        )
        # Deduplicate — same chunk may appear in multiple query results
        for doc, meta, id_ in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["ids"][0],
        ):
            if id_ not in seen_ids:
                seen_ids.add(id_)
                all_chunks.append(doc)
                all_metas.append(meta)

    # Limit total chunks sent to LLM
    all_chunks = all_chunks[:n_chunks]
    all_metas = all_metas[:n_chunks]

    # Step 4: Build context string with citations
    context_parts = []
    for i, (doc, meta) in enumerate(zip(all_chunks, all_metas)):
        context_parts.append(
            f"[Source {i+1} — {meta['source']}, Page {meta['page']}]:\n{doc}"
        )
    context = "\n\n".join(context_parts)

    # Step 5: Build RAG prompt
    prompt = f"""You are a helpful assistant that answers questions based on the provided context.

Rules:
- For specific factual questions: answer directly and cite the source and page number.
- For summary or abstract questions (key ideas, main points, important context, summarize):
  synthesize across ALL provided sources and give a comprehensive answer.
- If the answer truly cannot be found anywhere in the context, say "I don't have that information."
- Always mention page numbers when citing specific facts.

Context:
{context}

Question: {question}

Answer:"""

    # Step 6: Generate answer
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": [
            {
                "text": doc[:150],
                "page": meta["page"],
                "source": meta["source"],
            }
            for doc, meta in zip(all_chunks, all_metas)
        ],
    }


# ── Function 6: List all indexed documents ────────────────────────────────────

def list_indexed_documents() -> list[dict]:
    """
    Returns all indexed PDF collections with their chunk counts.
    Used by the frontend to populate the document list sidebar.
    """
    chroma = get_chroma_client()
    collections = chroma.list_collections()
    return [
        {
            "collection_name": col.name,
            "chunk_count": col.count(),
        }
        for col in collections
    ]


# ── Main: test pipeline locally ───────────────────────────────────────────────

if __name__ == "__main__":
    PDF_PATH = "sample.pdf"

    print("=== INDEXING ===")
    collection = index_pdf(PDF_PATH)

    print("\n=== QUERYING ===")
    questions = [
        "What is the main topic of this document?",
        "Who are the authors?",
        "What are the key ideas?",
    ]

    for q in questions:
        print(f"\nQ: {q}")
        result = rag_query(q, collection)
        print(f"A: {result['answer']}")
        print("Sources:")
        for s in result["sources"]:
            print(f"  → Page {s['page']}: {s['text'][:80]}...")
        print("-" * 60)

    print("\n=== INDEXED DOCUMENTS ===")
    for d in list_indexed_documents():
        print(f"  → {d['collection_name']} ({d['chunk_count']} chunks)")
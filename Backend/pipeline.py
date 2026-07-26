import os
import fitz  # PyMuPDF
import chromadb
from groq import Groq
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

# ── Initialize models and DB (done once at startup) ───────────────────────────

embed_model = SentenceTransformer("all-MiniLM-L6-v2")

chroma_client = chromadb.PersistentClient(path="./chroma_data")

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
)

# ── Helper: convert filename to valid collection name ─────────────────────────

def filename_to_collection_name(pdf_path: str) -> str:
    """
    ChromaDB collection names must be 3-63 characters,
    start with a letter, and contain only letters, numbers, or underscores.
    e.g. "my document.pdf" → "my_document_pdf"
    """
    name = os.path.basename(pdf_path)         # "my document.pdf"
    name = name.replace(".", "_")              # "my document_pdf"
    name = name.replace(" ", "_")             # "my_document_pdf"
    name = name.replace("-", "_")             # handle hyphens too
    name = name.lower()                       # lowercase for consistency
    return name

# ── Function 1: Extract text from PDF ─────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Opens a PDF and extracts text page by page.
    Returns a list of dicts: [{"page": 1, "text": "..."}, ...]
    We track page numbers so we can cite sources later.
    """
    doc = fitz.open(pdf_path)
    pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        # Skip pages with very little text (blank or image-only pages)
        if len(text.strip()) > 50:
            pages.append({
                "page": page_num + 1,
                "text": text
            })

    doc.close()
    print(f"Extracted text from {len(pages)} pages.")
    return pages

# ── Function 2: Chunk and index the PDF into ChromaDB ─────────────────────────

def index_pdf(pdf_path: str) -> chromadb.Collection:
    """
    Full ingestion pipeline:
    PDF → extract text → chunk → embed → store in ChromaDB

    Each PDF gets its own persistent collection named after the file.
    If the PDF was already indexed, we skip re-indexing.
    """
    collection_name = filename_to_collection_name(pdf_path)

    # Get or create a persistent collection for this specific PDF
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    # If already indexed, skip — no duplicate work
    if collection.count() > 0:
        print(f"'{collection_name}' already indexed ({collection.count()} chunks). Skipping.")
        return collection

    # Step 1: Extract text page by page
    pages = extract_text_from_pdf(pdf_path)

    # Step 2: Chunk each page's text
    all_chunks = []
    all_metadatas = []
    all_ids = []

    chunk_counter = 0
    for page_data in pages:
        page_chunks = splitter.split_text(page_data["text"])

        for chunk_text in page_chunks:
            # Skip chunks that are too short to be meaningful
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
    print("Embedding chunks... (this may take a moment)")
    embeddings = embed_model.encode(all_chunks, show_progress_bar=True).tolist()

    # Step 4: Store in ChromaDB in batches of 100
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        collection.add(
            ids=all_ids[i:i+batch_size],
            embeddings=embeddings[i:i+batch_size],
            documents=all_chunks[i:i+batch_size],
            metadatas=all_metadatas[i:i+batch_size],
        )

    print(f"Indexed {collection.count()} chunks into ChromaDB.\n")
    return collection
def generate_hypothetical_answer(question: str) -> str:
    """
    HyDE: Generate a fake answer to the question.
    This fake answer uses document-like vocabulary,
    so it retrieves better chunks than the raw question.
    """
    prompt = f"""You are an expert. Write a short, detailed paragraph 
that would be a perfect answer to the following question, 
as if you were reading it from a document.
Do not say you don't know. Just write what a good answer would look like.
Keep it under 150 words.

Question: {question}

Hypothetical answer:"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    return response.choices[0].message.content


def rewrite_query(question: str) -> list[str]:
    """
    Generate multiple search query variants for better retrieval.
    Returns original question + 3 rewrites.
    """
    prompt = f"""Generate 3 different search queries to find relevant 
content in a document for this question. Make them specific and varied.
Return ONLY a JSON array of 3 strings, nothing else.
Example: ["query 1", "query 2", "query 3"]

Question: {question}"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    import json
    try:
        queries = json.loads(response.choices[0].message.content)
        return [question] + queries
    except:
        return [question]
# ── Function 3: Answer a question using RAG ───────────────────────────────────

def rag_query(question: str, collection: chromadb.Collection, n_chunks: int = 5) -> dict:

    # ── Step 1: HyDE — generate hypothetical answer ───────────────────────────
    hypothetical = generate_hypothetical_answer(question)
    print(f"HyDE answer: {hypothetical[:100]}...")

    # ── Step 2: Multi-query rewriting ─────────────────────────────────────────
    queries = rewrite_query(question)
    print(f"Search queries: {queries}")

    # ── Step 3: Search with HyDE + all query variants ─────────────────────────
    all_search_texts = [hypothetical] + queries  # HyDE answer + rewrites
    seen_ids = set()
    all_chunks = []
    all_metas = []

    for search_text in all_search_texts:
        query_vector = embed_model.encode([search_text]).tolist()
        results = collection.query(
            query_embeddings=query_vector,
            n_results=3,
        )
        for doc, meta, id_ in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["ids"][0],
        ):
            if id_ not in seen_ids:
                seen_ids.add(id_)
                all_chunks.append(doc)
                all_metas.append(meta)

    # Limit total chunks
    all_chunks = all_chunks[:n_chunks]
    all_metas = all_metas[:n_chunks]

    # ── Step 4: Build context ──────────────────────────────────────────────────
    context_parts = []
    for i, (doc, meta) in enumerate(zip(all_chunks, all_metas)):
        context_parts.append(
            f"[Source {i+1} — {meta['source']}, Page {meta['page']}]:\n{doc}"
        )
    context = "\n\n".join(context_parts)

    # ── Step 5: Build prompt ───────────────────────────────────────────────────
    prompt = f"""You are a helpful assistant that answers questions based on the provided context.

Rules:
- For specific factual questions: answer directly and cite the source and page number.
- For summary or abstract questions (key ideas, main points, important context, what this is about):
  synthesize across ALL provided sources and give a comprehensive answer.
- If the answer truly cannot be found anywhere in the context, say "I don't have that information."
- Always mention page numbers when citing specific facts.

Context:
{context}

Question: {question}

Answer:"""

    # ── Step 6: Generate answer ────────────────────────────────────────────────
    response = groq_client.chat.completions.create(
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
# ── Function 4: List all indexed documents ────────────────────────────────────

def list_indexed_documents() -> list[dict]:
    """
    Returns a list of all PDFs that have been indexed.
    Useful for the frontend to show which documents are available.
    """
    collections = chroma_client.list_collections()
    documents = []
    for col in collections:
        documents.append({
            "collection_name": col.name,
            "chunk_count": col.count(),
        })
    return documents

# ── Main: test the full pipeline ──────────────────────────────────────────────

if __name__ == "__main__":
    PDF_PATH = "sample.pdf"

    print("=== INDEXING PDF ===")
    collection = index_pdf(PDF_PATH)

    print("=== QUERYING ===")
    questions = [
        "What is the Transformer architecture?",
        "What are the results on WMT translation tasks?",
        "Who are the authors?",
    ]

    for q in questions:
        print(f"\nQ: {q}")
        result = rag_query(q, collection)
        print(f"A: {result['answer']}")
        print("\nSources used:")
        for s in result["sources"]:
            print(f"  → Page {s['page']}: {s['text'][:100]}...")
        print("-" * 60)

    print("\n=== INDEXED DOCUMENTS ===")
    docs = list_indexed_documents()
    for d in docs:
        print(f"  → {d['collection_name']} ({d['chunk_count']} chunks)")
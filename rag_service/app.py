

import os
import json
import faiss
import numpy as np
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import google.generativeai as genai
from groq import Groq
import logging
import asyncio

# ================= CONFIG =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

FAISS_FILE = os.path.join(PARENT_DIR, "faiss_index.index")
META_FILE = os.path.join(PARENT_DIR, "meta.json")

TOP_K = 5
MODEL = "llama-3.1-8b-instant"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="RAG Chat API", version="1.0.0")

# CORS - مهم للـ streaming
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Keys
GEMINI_API_KEY = "AIzaSyAsMvD5vJbNl21Qc5NdIXfl2bw_D4ZOYAw"
GROQ_API_KEY = "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"

genai.configure(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

# ================= MODELS =================
class ChatRequest(BaseModel):
    query: str
    top_k: Optional[int] = TOP_K

# ================= HELPER FUNCTIONS =================
def embed_query(query: str) -> np.ndarray:
    try:
        resp = genai.embed_content(
            model="models/text-embedding-004",
            content=query,
            task_type="retrieval_query"
        )
        return np.array(resp["embedding"], dtype=np.float32)
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def retrieve_top_k(query: str, top_k: int = TOP_K) -> List[Dict]:
    try:
        logger.info(f"Looking for FAISS file at: {FAISS_FILE}")
        logger.info(f"Looking for META file at: {META_FILE}")
        
        if not os.path.exists(FAISS_FILE):
            raise HTTPException(status_code=404, detail=f"Index not found at: {FAISS_FILE}")
        if not os.path.exists(META_FILE):
            raise HTTPException(status_code=404, detail=f"Metadata not found at: {META_FILE}")
        
        index = faiss.read_index(FAISS_FILE)
        with open(META_FILE, encoding="utf-8") as f:
            metas = json.load(f)
        
        query_emb = embed_query(query)
        D, I = index.search(np.expand_dims(query_emb, 0), top_k)
        
        results = []
        for dist, idx in zip(D[0], I[0]):
            if idx == -1 or idx >= len(metas):
                continue
            meta = metas[idx]
            results.append({
                "distance": float(dist),
                "text": meta.get("text", "")[:1500],
                "url": meta.get("url", ""),
                "title": meta.get("title", "Unknown"),
                "position": meta.get("position", 0)
            })
        return results
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ================= ROUTES =================
@app.get("/")
async def root():
    return {"message": "RAG Chat API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "faiss_index_exists": os.path.exists(FAISS_FILE),
        "metadata_exists": os.path.exists(META_FILE),
        "faiss_path": FAISS_FILE,
        "meta_path": META_FILE
    }

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint with proper SSE streaming
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query empty")
    
    async def event_generator():
        try:
            # Step 1: Retrieve documents
            logger.info(f"Processing query: {query}")
            docs = retrieve_top_k(query, request.top_k)
            
            if not docs:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No docs found'})}\n\n"
                return
            
            # Step 2: Send sources immediately
            sources = {
                "type": "sources",
                "sources": [{
                    "title": d["title"],
                    "url": d["url"],
                    "snippet": d["text"][:250] + "...",
                    "distance": d["distance"],
                    "position": d["position"]
                } for d in docs]
            }
            yield f"data: {json.dumps(sources)}\n\n"
            await asyncio.sleep(0.01)  # مهم للـ streaming
            
            # Step 3: Prepare context
            context = "\n\n---\n\n".join([
                f"Source {i+1} - {d['title']}:\n{d['text']}"
                for i, d in enumerate(docs)
            ])
            
            prompt = (
                f"You are a helpful assistant. Use this context to answer:\n\n{context}\n\n"
                f"Question: {query}\n\nAnswer:"
            )
            
            # Step 4: Stream from Groq
            logger.info("Starting Groq streaming...")
            response = groq_client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=1000,
                stream=True
            )
            
            # Stream each chunk
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                    await asyncio.sleep(0.01)  # مهم جداً للـ streaming
            
            # Step 5: Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except HTTPException as e:
            logger.error(f"HTTP error: {e.detail}")
            yield f"data: {json.dumps({'type': 'error', 'message': e.detail})}\n\n"
        except Exception as e:
            logger.error(f"Error in generate: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # مهم لـ nginx
            "Content-Type": "text/event-stream",
        }
    )

if __name__ == "__main__":
    import uvicorn
    print(f"FAISS file path: {FAISS_FILE}")
    print(f"META file path: {META_FILE}")
    print(f"FAISS exists: {os.path.exists(FAISS_FILE)}")
    print(f"META exists: {os.path.exists(META_FILE)}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
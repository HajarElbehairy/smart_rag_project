import os
import json
import faiss
import numpy as np
import google.generativeai as genai
import hashlib
from datetime import datetime

# ================= CONFIG =================
INPUT_DIR = "chunks"                 # فولدر فيه JSON chunks
FAISS_FILE = "aiss_index.index"     # ملف الـ FAISS index
META_FILE = "meta.json"              # ملف metadata
INDEX_INFO_FILE = "index_info.json"  # معلومات عن آخر تحديث
BATCH_SIZE = 16                      

# Gemini API setup
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyAsMvD5vJbNl21Qc5NdIXfl2bw_D4ZOYAw"))

# ================= HELPER FUNCTIONS =================
def get_gemini_embeddings(texts, model="models/text-embedding-004"):
    """Compute embeddings for a batch of texts using Gemini"""
    embeddings = []
    for text in texts:
        try:
            resp = genai.embed_content(
                model=model, 
                content=text, 
                task_type="retrieval_document"
            )
            # استخدام المفتاح الصحيح للوصول للـ embedding
            embeddings.append(np.array(resp['embedding'], dtype=np.float32))
        except Exception as e:
            print(f"❌ Error embedding text: {e}")
            # في حالة الخطأ، نضيف vector فاضي بنفس الحجم
            if embeddings:
                embeddings.append(np.zeros_like(embeddings[0]))
            else:
                embeddings.append(np.zeros(768, dtype=np.float32))  # default dimension
    return embeddings

def load_chunks(input_dir):
    """Load all JSON chunks from directory"""
    texts, metas = [], []
    
    if not os.path.exists(input_dir):
        print(f"❌ Directory {input_dir} does not exist!")
        return texts, metas
    
    json_files = [f for f in os.listdir(input_dir) if f.endswith(".json")]
    
    for f in sorted(json_files):  # sorted للترتيب
        path = os.path.join(input_dir, f)
        try:
            with open(path, encoding="utf-8") as file:
                data = json.load(file)
            
            texts.append(data.get("text", ""))
            metas.append({
                "url": data.get("url", ""),
                "title": data.get("title", ""),
                "position": data.get("position", 0),
                "checksum": data.get("checksum", ""),
                "filename": f,
                "indexed_at": datetime.now().isoformat()
            })
        except Exception as e:
            print(f"⚠️ Error loading {f}: {e}")
    
    return texts, metas

def calculate_directory_hash(input_dir):
    """Calculate hash of all files in directory to detect changes"""
    hash_md5 = hashlib.md5()
    
    if not os.path.exists(input_dir):
        return None
    
    for filename in sorted(os.listdir(input_dir)):
        if filename.endswith(".json"):
            filepath = os.path.join(input_dir, filename)
            with open(filepath, 'rb') as f:
                hash_md5.update(f.read())
    
    return hash_md5.hexdigest()

def should_reindex(input_dir):
    """Check if re-indexing is needed based on content changes"""
    # إذا الملفات مش موجودة أصلاً
    if not os.path.exists(FAISS_FILE) or not os.path.exists(META_FILE):
        return True
    
    # إذا ملف index_info مش موجود
    if not os.path.exists(INDEX_INFO_FILE):
        return True
    
    # قراءة آخر hash
    try:
        with open(INDEX_INFO_FILE, 'r', encoding='utf-8') as f:
            index_info = json.load(f)
        last_hash = index_info.get('content_hash')
    except:
        return True
    
    # حساب الـ hash الحالي
    current_hash = calculate_directory_hash(input_dir)
    
    # مقارنة
    if last_hash != current_hash:
        print("🔄 Content changed detected. Re-indexing needed.")
        return True
    
    print("✅ Content unchanged. Using existing index.")
    return False

def save_index_info(content_hash, num_chunks):
    """Save indexing information"""
    info = {
        'content_hash': content_hash,
        'num_chunks': num_chunks,
        'indexed_at': datetime.now().isoformat(),
        'model': 'text-embedding-004'
    }
    with open(INDEX_INFO_FILE, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

# ================= RE-INDEX FUNCTION =================
def build_faiss_index(force_reindex=False):
    """Build or load FAISS index with smart re-indexing"""
    
    # Check if re-indexing is needed
    if not force_reindex and not should_reindex(INPUT_DIR):
        print("✅ Loading existing FAISS index...")
        index = faiss.read_index(FAISS_FILE)
        with open(META_FILE, encoding="utf-8") as f:
            metas = json.load(f)
        print(f"📊 Loaded index with {index.ntotal} vectors")
        return index, metas

    # Load chunks
    print("🔹 Starting indexing process...")
    texts, metas = load_chunks(INPUT_DIR)
    
    if len(texts) == 0:
        print("❌ No chunks found!")
        return None, []
    
    print(f"🔹 Loaded {len(texts)} chunks")

    # Compute embeddings in batches
    all_embeddings = []
    print("🔹 Computing embeddings...")
    
    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i:i+BATCH_SIZE]
        print(f"   Processing batch {i//BATCH_SIZE + 1}/{(len(texts)-1)//BATCH_SIZE + 1}...")
        batch_embs = get_gemini_embeddings(batch_texts)
        all_embeddings.extend(batch_embs)

    # Convert to numpy array
    embeddings_array = np.stack(all_embeddings)
    dim = embeddings_array.shape[1]
    print(f"🔹 Embedding dimension: {dim}")

    # Build FAISS index (L2 distance)
    print("🔹 Building FAISS index...")
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings_array)

    # Save FAISS index
    faiss.write_index(index, FAISS_FILE)
    print(f"✅ FAISS index saved: {FAISS_FILE}")
    
    # Save metadata
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False, indent=2)
    print(f"✅ Metadata saved: {META_FILE}")
    
    # Save index info
    content_hash = calculate_directory_hash(INPUT_DIR)
    save_index_info(content_hash, len(texts))
    print(f"✅ Index info saved: {INDEX_INFO_FILE}")
    
    print(f"📊 Total vectors indexed: {index.ntotal}")
    return index, metas

# ================= SEARCH FUNCTION (للاختبار) =================
def search_index(query, top_k=5):
    """Search the FAISS index for relevant chunks"""
    if not os.path.exists(FAISS_FILE):
        print("❌ Index not found! Please build it first.")
        return []
    
    # Load index and metadata
    index = faiss.read_index(FAISS_FILE)
    with open(META_FILE, encoding="utf-8") as f:
        metas = json.load(f)
    
    # Embed query
    print(f"🔍 Searching for: {query}")
    query_embedding = get_gemini_embeddings([query])[0]
    query_embedding = np.expand_dims(query_embedding, axis=0)
    
    # Search
    distances, indices = index.search(query_embedding, top_k)
    
    # Return results
    results = []
    for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
        if idx != -1:  # valid result
            results.append({
                'rank': i + 1,
                'distance': float(dist),
                'metadata': metas[idx]
            })
    
    return results

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 FAISS Indexing System")
    print("=" * 60)
    
    # Build or load index
    index, metas = build_faiss_index(force_reindex=False)  # غيري لـ True لو عايزة إعادة بناء
    
    if index is not None:
        print("\n" + "=" * 60)
        print("✅ Done. Index ready for retrieval.")
        print("=" * 60)
        
        # Test search (اختياري)
        print("\n🧪 Testing search functionality...")
        test_query = "machine learning"
        results = search_index(test_query, top_k=3)
        
        print(f"\nTop results for '{test_query}':")
        for result in results:
            print(f"\n{result['rank']}. Distance: {result['distance']:.4f}")
            print(f"   Title: {result['metadata']['title']}")
            print(f"   URL: {result['metadata']['url']}")
            print(f"   File: {result['metadata']['filename']}")
    else:
        print("❌ Failed to build index.")
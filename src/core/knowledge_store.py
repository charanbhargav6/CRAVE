"""
CRAVE Phase D — Knowledge Vector Store (ChromaDB)
==================================================
Fully OFFLINE semantic memory for CRAVE.

Stores:
  - Learned skills from Knowledge/skills/ (so "how do I use Docker?" 
    finds the skill by MEANING, not filename)
  - Conversation summaries (long-term memory beyond 50-msg context)
  - Trading insights from backtests

ChromaDB runs 100% locally — zero internet, zero cloud, zero API keys.
Data persists in D:\CRAVE\data\chromadb\

Install: pip install chromadb sentence-transformers
"""

import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("crave.core.knowledge_store")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
CHROMA_DIR = os.path.join(CRAVE_ROOT, "data", "chromadb")
SKILLS_DIR = os.path.join(CRAVE_ROOT, "Knowledge", "skills")

# ── Lazy imports — graceful if chromadb not installed ─────────────────────────

_chromadb = None
_client = None
_AVAILABLE = False


def _init_chroma():
    """Lazy-load ChromaDB client on first use."""
    global _chromadb, _client, _AVAILABLE
    if _client is not None:
        return _AVAILABLE
    try:
        import chromadb
        _chromadb = chromadb
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _AVAILABLE = True
        logger.info(f"[KnowledgeStore] ChromaDB initialized at {CHROMA_DIR}")
    except ImportError:
        _AVAILABLE = False
        logger.warning("[KnowledgeStore] chromadb not installed. Run: pip install chromadb sentence-transformers")
    except Exception as e:
        _AVAILABLE = False
        logger.error(f"[KnowledgeStore] ChromaDB init failed: {e}")
    return _AVAILABLE


def _get_collection(name: str):
    """Get or create a ChromaDB collection."""
    if not _init_chroma():
        return None
    return _client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}  # cosine similarity for text
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SKILLS COLLECTION — Learned knowledge from Research Agent
# ═══════════════════════════════════════════════════════════════════════════════

def index_skill(filepath: str) -> bool:
    """
    Index a single skill.md file into the vector store.
    Called by ResearchAgent after saving a new skill.
    
    Uses file hash as ID to prevent duplicates — re-indexing the same
    unchanged file is a no-op.
    """
    coll = _get_collection("skills")
    if coll is None:
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        if not content.strip():
            return False

        # Use content hash as document ID — prevents duplicates
        doc_id = hashlib.md5(content.encode()).hexdigest()
        filename = os.path.basename(filepath)
        
        # Chunk long documents (ChromaDB embedding models have token limits)
        chunks = _chunk_text(content, max_chars=1500)
        
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": filename, "chunk": i, "total_chunks": len(chunks)} 
                     for i in range(len(chunks))]
        
        coll.upsert(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )
        
        logger.info(f"[KnowledgeStore] Indexed skill: {filename} ({len(chunks)} chunks)")
        return True
    except Exception as e:
        logger.error(f"[KnowledgeStore] Failed to index {filepath}: {e}")
        return False


def index_all_skills() -> int:
    """
    Scan Knowledge/skills/ and index all .md files.
    Called on startup to ensure the vector store is up-to-date.
    Returns the number of files indexed.
    """
    if not _init_chroma():
        return 0
    
    if not os.path.exists(SKILLS_DIR):
        return 0
    
    count = 0
    for fname in os.listdir(SKILLS_DIR):
        if fname.endswith(".md"):
            fpath = os.path.join(SKILLS_DIR, fname)
            if index_skill(fpath):
                count += 1
    
    logger.info(f"[KnowledgeStore] Indexed {count} skills from {SKILLS_DIR}")
    return count


def search_skills(query: str, n_results: int = 3) -> List[Dict]:
    """
    Semantic search across all learned skills.
    Returns the top N most relevant skill chunks.
    
    Example:
        search_skills("how to connect to MetaTrader 5")
        → Returns chunks from mt5_skill.md even if the query doesn't 
          contain the exact words in the filename.
    """
    coll = _get_collection("skills")
    if coll is None:
        return []
    
    try:
        results = coll.query(
            query_texts=[query],
            n_results=n_results,
        )
        
        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0
                hits.append({
                    "content": doc,
                    "source": meta.get("source", "unknown"),
                    "relevance": round(1 - dist, 3),  # cosine: 1=perfect, 0=irrelevant
                })
        
        return hits
    except Exception as e:
        logger.error(f"[KnowledgeStore] Search failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATIONS COLLECTION — Long-term memory
# ═══════════════════════════════════════════════════════════════════════════════

def store_conversation_summary(summary: str, metadata: Optional[Dict] = None) -> bool:
    """
    Store a conversation summary for long-term recall.
    Called periodically by the Orchestrator when context is compressed.
    """
    coll = _get_collection("conversations")
    if coll is None:
        return False
    
    try:
        from datetime import datetime
        doc_id = hashlib.md5(summary.encode()).hexdigest()
        meta = metadata or {}
        meta["timestamp"] = datetime.utcnow().isoformat()
        
        coll.upsert(
            ids=[doc_id],
            documents=[summary],
            metadatas=[meta],
        )
        return True
    except Exception as e:
        logger.error(f"[KnowledgeStore] Failed to store conversation: {e}")
        return False


def recall_conversations(query: str, n_results: int = 3) -> List[Dict]:
    """
    Search past conversations by semantic meaning.
    "What did we talk about regarding trading?" → finds relevant past contexts.
    """
    coll = _get_collection("conversations")
    if coll is None:
        return []
    
    try:
        results = coll.query(query_texts=[query], n_results=n_results)
        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                hits.append({
                    "summary": doc,
                    "timestamp": meta.get("timestamp", "unknown"),
                    "relevance": round(1 - results["distances"][0][i], 3),
                })
        return hits
    except Exception as e:
        logger.error(f"[KnowledgeStore] Recall failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# TRADING INSIGHTS COLLECTION
# ═══════════════════════════════════════════════════════════════════════════════

def store_trading_insight(insight: str, symbol: str = "", metadata: Optional[Dict] = None) -> bool:
    """
    Store a trading insight (e.g., backtest summary, pattern observation).
    """
    coll = _get_collection("trading_insights")
    if coll is None:
        return False
    
    try:
        from datetime import datetime
        doc_id = hashlib.md5(insight.encode()).hexdigest()
        meta = metadata or {}
        meta["symbol"] = symbol
        meta["timestamp"] = datetime.utcnow().isoformat()
        
        coll.upsert(ids=[doc_id], documents=[insight], metadatas=[meta])
        return True
    except Exception as e:
        logger.error(f"[KnowledgeStore] Failed to store insight: {e}")
        return False


def search_trading_insights(query: str, n_results: int = 3) -> List[Dict]:
    """Search past trading insights semantically."""
    coll = _get_collection("trading_insights")
    if coll is None:
        return []
    
    try:
        results = coll.query(query_texts=[query], n_results=n_results)
        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                hits.append({
                    "insight": doc,
                    "symbol": meta.get("symbol", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "relevance": round(1 - results["distances"][0][i], 3),
                })
        return hits
    except Exception as e:
        logger.error(f"[KnowledgeStore] Search insights failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _chunk_text(text: str, max_chars: int = 1500) -> List[str]:
    """
    Split text into chunks at paragraph boundaries.
    ChromaDB's default embedding model has token limits (~512 tokens).
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    
    for para in paragraphs:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para if current else para
    
    if current.strip():
        chunks.append(current.strip())
    
    return chunks if chunks else [text[:max_chars]]


def get_status() -> Dict:
    """Return the current status of the knowledge store."""
    if not _init_chroma():
        return {"available": False, "reason": "chromadb not installed"}
    
    try:
        skills = _get_collection("skills")
        convos = _get_collection("conversations")
        trades = _get_collection("trading_insights")
        
        return {
            "available": True,
            "path": CHROMA_DIR,
            "collections": {
                "skills": skills.count() if skills else 0,
                "conversations": convos.count() if convos else 0,
                "trading_insights": trades.count() if trades else 0,
            }
        }
    except Exception as e:
        return {"available": True, "error": str(e)}

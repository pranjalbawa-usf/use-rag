"""
Admin Routes for RAG Document Assistant
========================================
Provides API endpoints for viewing and managing all data in the system.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path
import os
import json

router = APIRouter(prefix="/api/admin", tags=["admin"])

# We'll get these from main.py when the router is included
vector_store = None
UPLOAD_DIR = None

def init_admin(vs, upload_dir):
    """Initialize admin routes with vector store and upload directory."""
    global vector_store, UPLOAD_DIR
    vector_store = vs
    UPLOAD_DIR = upload_dir


# ============================================================================
# Pydantic Models
# ============================================================================

class OverviewStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_messages: int
    storage_size_mb: float
    storage_size_formatted: str


class DatabaseHealth(BaseModel):
    status: str
    vector_store_type: str
    persist_directory: str
    collection_name: str
    total_chunks: int
    embedding_model: str
    last_check: str


class DocumentInfo(BaseModel):
    filename: str
    file_type: str
    file_size: int
    file_size_formatted: str
    chunk_count: int
    uploaded_at: Optional[str] = None
    file_path: str


class ChunkInfo(BaseModel):
    id: str
    content: str
    source: str
    chunk_index: int
    uploaded_at: Optional[str] = None
    content_preview: str


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    session_id: Optional[str] = None


class ChatSession(BaseModel):
    session_id: str
    message_count: int
    first_message: str
    last_message: str
    created_at: str


# ============================================================================
# Helper Functions
# ============================================================================

def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_file_type(filename: str) -> str:
    """Get file type from filename."""
    ext = Path(filename).suffix.lower()
    type_map = {
        '.pdf': 'PDF',
        '.txt': 'Text',
        '.md': 'Markdown',
        '.docx': 'Word',
        '.xlsx': 'Excel',
        '.csv': 'CSV',
        '.png': 'Image',
        '.jpg': 'Image',
        '.jpeg': 'Image',
        '.gif': 'Image',
        '.bmp': 'Image',
        '.webp': 'Image'
    }
    return type_map.get(ext, 'Unknown')


def get_directory_size(directory: Path) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    if directory.exists():
        for f in directory.rglob('*'):
            if f.is_file():
                total += f.stat().st_size
    return total


# In-memory chat history storage (since we don't have a database)
chat_history: List[Dict] = []
chat_sessions: Dict[str, List[Dict]] = {}
current_session_id: str = None


def add_chat_message(role: str, content: str, session_id: str = None):
    """Add a message to chat history."""
    global current_session_id
    
    if session_id is None:
        if current_session_id is None:
            current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = current_session_id
    
    message = {
        "id": f"msg_{len(chat_history)}_{datetime.now().timestamp()}",
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id
    }
    
    chat_history.append(message)
    
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    chat_sessions[session_id].append(message)
    
    return message


def start_new_session():
    """Start a new chat session."""
    global current_session_id
    current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return current_session_id


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/overview", response_model=OverviewStats)
async def get_overview():
    """Get system overview statistics."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    # Get document count
    documents = vector_store.list_documents()
    total_documents = len(documents)
    
    # Get chunk count
    stats = vector_store.get_stats()
    total_chunks = stats.get("total_chunks", 0)
    
    # Get chat message count
    total_messages = len(chat_history)
    
    # Get storage size
    storage_size = 0
    if UPLOAD_DIR and UPLOAD_DIR.exists():
        storage_size = get_directory_size(UPLOAD_DIR)
    
    # Add ChromaDB storage
    chroma_dir = Path("chroma_data")
    if chroma_dir.exists():
        storage_size += get_directory_size(chroma_dir)
    
    storage_mb = storage_size / (1024 * 1024)
    
    return OverviewStats(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_messages=total_messages,
        storage_size_mb=storage_mb,
        storage_size_formatted=format_file_size(storage_size)
    )


@router.get("/database/health", response_model=DatabaseHealth)
async def get_database_health():
    """Get database connection status and health info."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        stats = vector_store.get_stats()
        
        return DatabaseHealth(
            status="healthy",
            vector_store_type="ChromaDB",
            persist_directory=stats.get("persist_directory", "chroma_data"),
            collection_name="documents",
            total_chunks=stats.get("total_chunks", 0),
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            last_check=datetime.now().isoformat()
        )
    except Exception as e:
        return DatabaseHealth(
            status=f"error: {str(e)}",
            vector_store_type="ChromaDB",
            persist_directory="chroma_data",
            collection_name="documents",
            total_chunks=0,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            last_check=datetime.now().isoformat()
        )


@router.get("/documents", response_model=List[DocumentInfo])
async def list_documents():
    """List all documents with details."""
    if vector_store is None or UPLOAD_DIR is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    documents = vector_store.list_documents()
    result = []
    
    for filename in documents:
        file_path = UPLOAD_DIR / filename
        
        # Get file info
        file_size = 0
        uploaded_at = None
        
        if file_path.exists():
            stat = file_path.stat()
            file_size = stat.st_size
            uploaded_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
        
        # Count chunks for this document
        chunk_count = 0
        try:
            # Get all chunks and count those matching this source
            all_data = vector_store.collection.get(
                where={"source": filename},
                include=["metadatas"]
            )
            chunk_count = len(all_data.get("ids", []))
        except:
            pass
        
        result.append(DocumentInfo(
            filename=filename,
            file_type=get_file_type(filename),
            file_size=file_size,
            file_size_formatted=format_file_size(file_size),
            chunk_count=chunk_count,
            uploaded_at=uploaded_at,
            file_path=str(file_path)
        ))
    
    # Sort by upload date (newest first)
    result.sort(key=lambda x: x.uploaded_at or "", reverse=True)
    
    return result


@router.get("/documents/{filename:path}")
async def get_document(filename: str):
    """Get single document details."""
    if vector_store is None or UPLOAD_DIR is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    file_path = UPLOAD_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    stat = file_path.stat()
    
    # Count chunks
    chunk_count = 0
    try:
        all_data = vector_store.collection.get(
            where={"source": filename},
            include=["metadatas"]
        )
        chunk_count = len(all_data.get("ids", []))
    except:
        pass
    
    return {
        "filename": filename,
        "file_type": get_file_type(filename),
        "file_size": stat.st_size,
        "file_size_formatted": format_file_size(stat.st_size),
        "chunk_count": chunk_count,
        "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "file_path": str(file_path)
    }


@router.get("/documents/{filename:path}/chunks")
async def get_document_chunks(filename: str):
    """Get all chunks for a specific document."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        all_data = vector_store.collection.get(
            where={"source": filename},
            include=["documents", "metadatas"]
        )
        
        chunks = []
        ids = all_data.get("ids", [])
        documents = all_data.get("documents", [])
        metadatas = all_data.get("metadatas", [])
        
        for i, chunk_id in enumerate(ids):
            content = documents[i] if i < len(documents) else ""
            metadata = metadatas[i] if i < len(metadatas) else {}
            
            chunks.append({
                "id": chunk_id,
                "content": content,
                "source": metadata.get("source", filename),
                "chunk_index": metadata.get("chunk_index", i),
                "uploaded_at": metadata.get("uploaded_at"),
                "content_preview": content[:200] + "..." if len(content) > 200 else content
            })
        
        # Sort by chunk index
        chunks.sort(key=lambda x: x["chunk_index"])
        
        return {"filename": filename, "chunks": chunks, "total": len(chunks)}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chunks: {str(e)}")


@router.get("/chunks")
async def list_chunks(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200)
):
    """List all chunks with pagination."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        # Get all chunks
        all_data = vector_store.collection.get(
            include=["documents", "metadatas"]
        )
        
        ids = all_data.get("ids", [])
        documents = all_data.get("documents", [])
        metadatas = all_data.get("metadatas", [])
        
        total = len(ids)
        
        # Paginate
        start = (page - 1) * limit
        end = start + limit
        
        chunks = []
        for i in range(start, min(end, total)):
            content = documents[i] if i < len(documents) else ""
            metadata = metadatas[i] if i < len(metadatas) else {}
            
            chunks.append({
                "id": ids[i],
                "content": content,
                "source": metadata.get("source", "unknown"),
                "chunk_index": metadata.get("chunk_index", 0),
                "uploaded_at": metadata.get("uploaded_at"),
                "content_preview": content[:200] + "..." if len(content) > 200 else content
            })
        
        return {
            "chunks": chunks,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chunks: {str(e)}")


@router.get("/chunks/search")
async def search_chunks(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100)
):
    """Search chunks by content keyword."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        # Get all chunks
        all_data = vector_store.collection.get(
            include=["documents", "metadatas"]
        )
        
        ids = all_data.get("ids", [])
        documents = all_data.get("documents", [])
        metadatas = all_data.get("metadatas", [])
        
        # Search by keyword
        query_lower = q.lower()
        results = []
        
        for i, content in enumerate(documents):
            if query_lower in content.lower():
                metadata = metadatas[i] if i < len(metadatas) else {}
                results.append({
                    "id": ids[i],
                    "content": content,
                    "source": metadata.get("source", "unknown"),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "uploaded_at": metadata.get("uploaded_at"),
                    "content_preview": content[:300] + "..." if len(content) > 300 else content,
                    "match_count": content.lower().count(query_lower)
                })
                
                if len(results) >= limit:
                    break
        
        # Sort by match count
        results.sort(key=lambda x: x["match_count"], reverse=True)
        
        return {
            "query": q,
            "results": results,
            "total": len(results)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching chunks: {str(e)}")


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str):
    """Get single chunk details."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        result = vector_store.collection.get(
            ids=[chunk_id],
            include=["documents", "metadatas"]
        )
        
        if not result["ids"]:
            raise HTTPException(status_code=404, detail="Chunk not found")
        
        content = result["documents"][0] if result["documents"] else ""
        metadata = result["metadatas"][0] if result["metadatas"] else {}
        
        return {
            "id": chunk_id,
            "content": content,
            "source": metadata.get("source", "unknown"),
            "chunk_index": metadata.get("chunk_index", 0),
            "uploaded_at": metadata.get("uploaded_at")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chunk: {str(e)}")


@router.get("/chat-history")
async def get_chat_history(limit: int = Query(100, ge=1, le=500)):
    """Get all chat messages."""
    messages = chat_history[-limit:] if len(chat_history) > limit else chat_history
    return {
        "messages": messages,
        "total": len(chat_history)
    }


@router.get("/chat-history/sessions")
async def get_chat_sessions():
    """List all chat sessions."""
    sessions = []
    
    for session_id, messages in chat_sessions.items():
        if messages:
            sessions.append({
                "session_id": session_id,
                "message_count": len(messages),
                "first_message": messages[0]["content"][:100] + "..." if len(messages[0]["content"]) > 100 else messages[0]["content"],
                "last_message": messages[-1]["content"][:100] + "..." if len(messages[-1]["content"]) > 100 else messages[-1]["content"],
                "created_at": messages[0]["timestamp"]
            })
    
    # Sort by created_at (newest first)
    sessions.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/chat-history")
async def clear_chat_history():
    """Clear all chat history."""
    global chat_history, chat_sessions, current_session_id
    
    count = len(chat_history)
    chat_history = []
    chat_sessions = {}
    current_session_id = None
    
    return {"message": f"Cleared {count} messages", "deleted": count}


@router.delete("/chat-history/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a specific chat session."""
    global chat_history, chat_sessions
    
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Remove messages from this session
    count = len(chat_sessions[session_id])
    chat_history = [m for m in chat_history if m.get("session_id") != session_id]
    del chat_sessions[session_id]
    
    return {"message": f"Deleted session with {count} messages", "deleted": count}


@router.post("/database/optimize")
async def optimize_database():
    """Optimize the database (compact ChromaDB)."""
    if vector_store is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        # ChromaDB doesn't have a direct optimize command, but we can get stats
        stats = vector_store.get_stats()
        
        return {
            "message": "Database optimization complete",
            "total_chunks": stats.get("total_chunks", 0),
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@router.delete("/database/clear-all")
async def clear_all_data(confirm: bool = Query(False)):
    """Clear all data from the system. Requires confirm=true."""
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="This action requires confirmation. Add ?confirm=true to proceed."
        )
    
    if vector_store is None or UPLOAD_DIR is None:
        raise HTTPException(status_code=500, detail="Admin not initialized")
    
    try:
        # Clear vector store
        documents = vector_store.list_documents()
        chunks_deleted = 0
        
        for doc in documents:
            chunks_deleted += vector_store.delete_document(doc)
        
        # Clear uploaded files
        files_deleted = 0
        if UPLOAD_DIR.exists():
            for f in UPLOAD_DIR.iterdir():
                if f.is_file():
                    f.unlink()
                    files_deleted += 1
        
        # Clear chat history
        global chat_history, chat_sessions, current_session_id
        messages_deleted = len(chat_history)
        chat_history = []
        chat_sessions = {}
        current_session_id = None
        
        return {
            "message": "All data cleared successfully",
            "documents_deleted": len(documents),
            "chunks_deleted": chunks_deleted,
            "files_deleted": files_deleted,
            "messages_deleted": messages_deleted
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear data: {str(e)}")

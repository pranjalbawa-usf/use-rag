"""
RAG System - Main FastAPI Server
=================================
This is the entry point for the RAG application.

It provides:
- REST API endpoints for uploading documents and asking questions
- Static file serving for the web interface
- Health check endpoint

Run with: python main.py
Then open: http://localhost:8000
"""

import os
import asyncio
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from document_processor import DocumentProcessor
from vector_store import VectorStore
from rag_engine import RAGEngine
from admin_routes import router as admin_router, init_admin

# Create necessary directories
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

# Initialize components
# These are created once when the server starts
print("=" * 50)
print("Initializing RAG System...")
print("=" * 50)

document_processor = DocumentProcessor(chunk_size=350, chunk_overlap=35)
vector_store = VectorStore(persist_directory="chroma_data")
rag_engine = RAGEngine(vector_store)

print("=" * 50)
print("RAG System Ready!")
print("=" * 50)

# Initialize admin routes with vector store and upload directory
init_admin(vector_store, UPLOAD_DIR)

# Create FastAPI app
app = FastAPI(
    title="USF RAG System",
    description="A simple RAG chatbot that answers questions about your documents",
    version="1.0.0"
)

# Allow CORS (needed if frontend is served separately during development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include admin routes
app.include_router(admin_router)


# ============================================================================
# Pydantic Models (for request/response validation)
# ============================================================================

class ChatRequest(BaseModel):
    """Request body for asking a question."""
    question: str
    n_chunks: Optional[int] = 5  # How many context chunks to use (default 5 for better context)
    filter_sources: Optional[List[str]] = None  # Filter search to specific documents


class ChatResponse(BaseModel):
    """Response body for a question answer."""
    answer: str
    sources: List[str]
    chunks_used: List[dict]


class DocumentInfo(BaseModel):
    """Information about an uploaded document."""
    filename: str
    chunks: int


class FileUploadResult(BaseModel):
    """Result of a single file upload."""
    filename: str
    status: str  # 'success' or 'error'
    chunks: Optional[int] = None
    error: Optional[str] = None


class MultiUploadResponse(BaseModel):
    """Response for multi-file upload."""
    total_files: int
    successful: int
    failed: int
    results: List[FileUploadResult]


class StatsResponse(BaseModel):
    """System statistics."""
    total_chunks: int
    documents: List[str]


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Serve the main web interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint - useful for monitoring."""
    return {"status": "healthy", "message": "RAG system is running!"}


async def process_single_file(file: UploadFile) -> FileUploadResult:
    """
    Process a single file upload. Used by both single and multi-upload endpoints.
    Returns FileUploadResult with status.
    """
    filename = file.filename
    
    # Read file content to get size
    content = await file.read()
    file_size = len(content)
    
    # Validate file
    validation = DocumentProcessor.validate_file(filename, file_size)
    if not validation['valid']:
        return FileUploadResult(
            filename=filename,
            status='error',
            error=validation['error']
        )
    
    # Save the file
    file_path = UPLOAD_DIR / filename
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)
    except Exception as e:
        return FileUploadResult(
            filename=filename,
            status='error',
            error=f"Failed to save file: {str(e)}"
        )
    
    # Process the document
    try:
        # Use async processing for speed
        chunks = await document_processor.process_document_async(str(file_path))
        
        # Convert to dict format for vector store
        chunk_dicts = [chunk.to_dict() for chunk in chunks]
        
        # Add to vector store (async)
        await vector_store.add_documents_async(chunk_dicts)
        
        return FileUploadResult(
            filename=filename,
            status='success',
            chunks=len(chunks)
        )
    
    except Exception as e:
        # Clean up the file if processing failed
        if file_path.exists():
            file_path.unlink()
        return FileUploadResult(
            filename=filename,
            status='error',
            error=f"Failed to process: {str(e)}"
        )


@app.post("/upload", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a single document to be processed and indexed.
    
    Supports: .txt, .md, .pdf files (max 10MB)
    """
    result = await process_single_file(file)
    
    if result.status == 'error':
        raise HTTPException(status_code=400, detail=result.error)
    
    return DocumentInfo(filename=result.filename, chunks=result.chunks)


@app.post("/upload-multiple", response_model=MultiUploadResponse)
async def upload_multiple_documents(files: List[UploadFile] = File(...)):
    """
    Upload multiple documents at once (up to 10 files, 50MB total).
    
    Files are processed in parallel for speed.
    Returns status for each file - continues even if some fail.
    """
    print(f"\n{'='*50}")
    print(f"Multi-file upload: {len(files)} files")
    print(f"{'='*50}")
    
    # Validate batch
    file_info = []
    for f in files:
        content = await f.read()
        file_info.append({'filename': f.filename, 'size': len(content)})
        # Reset file position for later reading
        await f.seek(0)
    
    batch_validation = DocumentProcessor.validate_batch(file_info)
    if not batch_validation['valid']:
        raise HTTPException(status_code=400, detail=batch_validation['error'])
    
    # Process all files in parallel
    start_time = datetime.now()
    tasks = [process_single_file(file) for file in files]
    results = await asyncio.gather(*tasks)
    
    # Calculate stats
    successful = sum(1 for r in results if r.status == 'success')
    failed = len(results) - successful
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"✓ Processed {len(files)} files in {elapsed:.2f}s ({successful} success, {failed} failed)")
    
    return MultiUploadResponse(
        total_files=len(files),
        successful=successful,
        failed=failed,
        results=results
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Ask a question about your documents (main chat endpoint).
    
    The system will:
    1. Search for relevant document chunks (top 5 by default)
    2. Send them to USF model as context
    3. Return USF's answer with source citations
    """
    print(f"\n{'='*50}")
    print(f"New question: {request.question[:100]}..." if len(request.question) > 100 else f"New question: {request.question}")
    print(f"{'='*50}")
    
    # Validate the question
    if not request.question.strip():
        raise HTTPException(
            status_code=400, 
            detail="Question cannot be empty. Please type a question about your documents."
        )
    
    # Validate n_chunks
    n_chunks = max(1, min(request.n_chunks, 10))  # Clamp between 1 and 10
    
    try:
        result = rag_engine.query(
            question=request.question,
            n_chunks=n_chunks,
            upload_dir=str(UPLOAD_DIR)
        )
        
        print(f"✓ Response ready (sources: {result['sources']})")
        
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            chunks_used=result["chunks_used"]
        )
    
    except ValueError as e:
        # ValueError is raised by RAGEngine for API errors (auth, rate limit, etc.)
        print(f"✗ Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        # Unexpected errors
        print(f"✗ Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Something went wrong while processing your question. Please try again. Error: {str(e)}"
        )


# Keep /query as an alias for backwards compatibility
@app.post("/query", response_model=ChatResponse, include_in_schema=False)
async def query_documents(request: ChatRequest):
    """Alias for /chat endpoint (backwards compatibility)."""
    return await chat(request)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming chat endpoint - returns response word-by-word for better UX.
    Uses Server-Sent Events (SSE) format.
    """
    print(f"\n{'='*50}")
    print(f"[STREAM] New question: {request.question[:100]}...")
    print(f"{'='*50}")
    
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    
    # Validate n_chunks
    n_chunks = max(1, min(request.n_chunks, 10))  # Clamp between 1 and 10
    
    # Get relevant chunks first (this is fast)
    # If filter_sources is provided, only search within those documents
    chunks = vector_store.search(
        request.question, 
        n_results=n_chunks,
        filter_sources=request.filter_sources,
        upload_dir=str(UPLOAD_DIR)
    )
    
    if not chunks:
        async def no_docs_response():
            if request.filter_sources:
                yield "data: The document(s) you uploaded no longer exist on the server. Please remove them from the chat and upload fresh copies.\n\n"
            else:
                yield "data: I don't have any documents to search through yet. Please upload some documents first!\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(no_docs_response(), media_type="text/event-stream")
    
    # Get unique sources for the response
    sources = list(set(chunk["source"] for chunk in chunks))
    
    async def generate():
        try:
            # Stream from USF API
            for chunk in rag_engine.usf_service.generate_answer_stream(request.question, chunks):
                yield f"data: {chunk}\n\n"
            # Send sources at the end
            yield f"data: [SOURCES]{','.join(sources)}[/SOURCES]\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR]{str(e)}[/ERROR]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get statistics about the indexed documents."""
    stats = vector_store.get_stats()
    documents = vector_store.list_documents()
    
    return StatsResponse(
        total_chunks=stats["total_chunks"],
        documents=documents
    )


@app.delete("/document/{filename}")
async def delete_document(filename: str):
    """
    Delete a document from the system.
    
    This removes:
    1. The file from uploads directory
    2. All chunks from the vector store
    """
    # Delete from vector store
    chunks_deleted = vector_store.delete_document(filename)
    
    # Delete the file if it exists
    file_path = UPLOAD_DIR / filename
    file_deleted = False
    if file_path.exists():
        file_path.unlink()
        file_deleted = True
    
    return {
        "filename": filename,
        "chunks_deleted": chunks_deleted,
        "file_deleted": file_deleted
    }


@app.get("/documents")
async def list_documents():
    """List all indexed documents that actually exist on disk."""
    all_documents = vector_store.list_documents()
    
    # Filter to only include documents that exist in uploads folder
    existing_documents = []
    orphaned_documents = []
    for doc in all_documents:
        file_path = UPLOAD_DIR / doc
        if file_path.exists():
            existing_documents.append(doc)
        else:
            orphaned_documents.append(doc)
    
    # Auto-cleanup orphaned documents from vector store
    for orphan in orphaned_documents:
        print(f"  Cleaning up orphaned document from vector store: {orphan}")
        vector_store.delete_document(orphan)
    
    return {"documents": existing_documents}


@app.get("/file")
async def get_document_file(name: str):
    """
    Serve the actual document file for preview (especially PDFs).
    Use query parameter: /file?name=filename.pdf
    """
    from fastapi.responses import FileResponse
    from urllib.parse import unquote
    import unicodedata
    
    filename = unquote(name)
    file_path = UPLOAD_DIR / filename
    
    # If file not found, try to find a matching file with different unicode spaces
    if not file_path.exists():
        # Try to find the file by normalizing unicode
        for f in UPLOAD_DIR.iterdir():
            # Normalize both filenames for comparison
            normalized_input = unicodedata.normalize('NFKC', filename)
            normalized_file = unicodedata.normalize('NFKC', f.name)
            if normalized_input == normalized_file:
                file_path = f
                filename = f.name
                break
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    ext = file_path.suffix.lower()
    media_types = {
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.csv': 'text/csv'
    }
    
    # Use headers to display inline instead of download
    # Sanitize filename for HTTP header (ASCII only)
    safe_filename = filename.encode('ascii', 'ignore').decode('ascii').replace(' ', '_')
    return FileResponse(
        path=str(file_path),
        media_type=media_types.get(ext, 'application/octet-stream'),
        headers={"Content-Disposition": f"inline; filename={safe_filename}"}
    )


@app.get("/json")
async def get_document_json(name: str):
    """
    Extract structured JSON from a document using Vision AI OCR.
    Use query parameter: /json?name=filename.pdf
    """
    from urllib.parse import unquote
    import unicodedata
    from ocr_service import ocr_service
    
    filename = unquote(name)
    file_path = UPLOAD_DIR / filename
    
    # If file not found, try to find a matching file with different unicode spaces
    if not file_path.exists():
        for f in UPLOAD_DIR.iterdir():
            normalized_input = unicodedata.normalize('NFKC', filename)
            normalized_file = unicodedata.normalize('NFKC', f.name)
            if normalized_input == normalized_file:
                file_path = f
                filename = f.name
                break
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    ext = file_path.suffix.lower()
    
    # For images, extract JSON directly
    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
        json_data = ocr_service.extract_structured_json(str(file_path))
        return {"filename": filename, "type": "image", "data": json_data}
    
    # For PDFs, convert first page to image and extract
    elif ext == '.pdf':
        try:
            import fitz
            import tempfile
            
            doc = fitz.open(str(file_path))
            if len(doc) == 0:
                return {"filename": filename, "type": "pdf", "data": {"error": "Empty PDF"}}
            
            # Extract from first page
            page = doc[0]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pix.save(tmp.name)
                tmp_path = tmp.name
            
            json_data = ocr_service.extract_structured_json(tmp_path)
            
            # Clean up
            Path(tmp_path).unlink()
            doc.close()
            
            return {"filename": filename, "type": "pdf", "data": json_data}
        except Exception as e:
            return {"filename": filename, "type": "pdf", "data": {"error": str(e)}}
    
    else:
        return {"filename": filename, "type": ext, "data": {"error": "JSON extraction not supported for this file type"}}


@app.get("/content")
async def get_document_content(name: str):
    """
    Get the content of a document for preview.
    Use query parameter: /content?name=filename.pdf
    """
    from urllib.parse import unquote
    import unicodedata
    
    filename = unquote(name)
    file_path = UPLOAD_DIR / filename
    
    # If file not found, try to find a matching file with different unicode spaces
    if not file_path.exists():
        for f in UPLOAD_DIR.iterdir():
            normalized_input = unicodedata.normalize('NFKC', filename)
            normalized_file = unicodedata.normalize('NFKC', f.name)
            if normalized_input == normalized_file:
                file_path = f
                filename = f.name
                break
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        # Read the file content
        ext = file_path.suffix.lower()
        
        if ext == '.pdf':
            # For PDFs, try to extract text using PyMuPDF
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(file_path))
                content = ""
                num_pages = len(doc)
                
                for page_num, page in enumerate(doc):
                    page_text = page.get_text()
                    if page_text.strip():
                        content += f"--- Page {page_num + 1} ---\n{page_text}\n\n"
                
                doc.close()
                
                # If no text was extracted, it might be a scanned PDF
                if not content.strip():
                    content = f"[This PDF contains {num_pages} page(s) but no extractable text.\n\nThis may be a scanned document or image-based PDF.\n\nThe document has been indexed and you can still ask questions about it in the chat - the system will use the processed content from when it was uploaded.]"
                    
            except ImportError:
                content = "[PDF preview requires PyMuPDF. Install with: pip install pymupdf]"
            except Exception as e:
                content = f"[Could not extract PDF text: {str(e)}]"
        elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
            # For images, return a marker that frontend will use to display the image
            content = f"[IMAGE_FILE:{filename}]"
        elif ext == '.docx':
            # For Word documents
            try:
                from docx import Document
                doc = Document(str(file_path))
                content = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                if not content.strip():
                    content = "[No text content found in this Word document]"
            except Exception as e:
                content = f"[Could not read Word document: {str(e)}]"
        elif ext == '.xlsx':
            # For Excel files
            try:
                from openpyxl import load_workbook
                wb = load_workbook(str(file_path), data_only=True)
                lines = []
                for sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    lines.append(f"=== Sheet: {sheet_name} ===")
                    for row in sheet.iter_rows(values_only=True):
                        row_values = [str(cell) if cell is not None else "" for cell in row]
                        if any(v.strip() for v in row_values):
                            lines.append(" | ".join(row_values))
                content = "\n".join(lines)
            except Exception as e:
                content = f"[Could not read Excel file: {str(e)}]"
        elif ext == '.csv':
            # For CSV files
            import csv
            lines = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if any(cell.strip() for cell in row):
                        lines.append(" | ".join(row))
            content = "\n".join(lines)
        else:
            # For text files (.txt, .md)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        # Limit content length for preview
        max_preview_length = 50000
        if len(content) > max_preview_length:
            content = content[:max_preview_length] + "\n\n... [Content truncated for preview]"
        
        return {"filename": filename, "content": content}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading document: {str(e)}")


# Mount static files (CSS, JS)
# This must be after the API routes so they take precedence
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================================
# Run the server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "=" * 50)
    print("Starting RAG Server...")
    print("Open http://localhost:8000 in your browser")
    print("=" * 50 + "\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Auto-reload on code changes (great for development!)
    )

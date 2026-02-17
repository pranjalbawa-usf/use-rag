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
from web_search_service import WebSearchService
from query_analyzer import QueryAnalyzer, SearchIntent

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
web_search = WebSearchService()
query_analyzer = QueryAnalyzer()

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


@app.get("/login")
async def login_page():
    """Serve the login page."""
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/health")
async def health_check():
    """Health check endpoint - useful for monitoring."""
    return {"status": "healthy", "message": "RAG system is running!"}


async def process_single_file(file: UploadFile) -> FileUploadResult:
    """
    Process a single file upload. Used by both single and multi-upload endpoints.
    Returns FileUploadResult with status.
    
    For images: Uses quick local processing first, then enhances with Vision API in background.
    For other files: Processes normally (fast for text/PDF).
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
    
    # Check if it's an image - use quick indexing first
    ext = Path(filename).suffix.lower()
    is_image = ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']
    
    # Process the document - all processing happens in background for instant uploads
    try:
        if is_image:
            # For images: Quick index with filename only, then process OCR in background
            quick_chunk = {
                "content": f"[Image: {filename}] Processing...",
                "source": filename,
                "chunk_index": 0
            }
            await vector_store.add_documents_async([quick_chunk])
            
            # Start background OCR processing
            asyncio.create_task(process_image_ocr_background(str(file_path), filename))
            
            return FileUploadResult(
                filename=filename,
                status='success',
                chunks=1
            )
        else:
            # For non-images: Quick index first, then process in background
            quick_chunk = {
                "content": f"[Document: {filename}] Processing...",
                "source": filename,
                "chunk_index": 0
            }
            await vector_store.add_documents_async([quick_chunk])
            
            # Start background document processing
            asyncio.create_task(process_document_background(str(file_path), filename))
            
            return FileUploadResult(
                filename=filename,
                status='success',
                chunks=1
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


async def process_image_ocr_background(file_path: str, filename: str):
    """
    Background task to process image OCR and update vector store.
    This runs after the upload response is sent to the user.
    """
    try:
        print(f"  [Background] Starting OCR for {filename}...")
        
        # Process the image with full OCR
        chunks = await document_processor.process_document_async(file_path)
        
        if chunks:
            # Delete the placeholder chunk
            vector_store.delete_document(filename)
            
            # Add the real chunks
            chunk_dicts = [chunk.to_dict() for chunk in chunks]
            await vector_store.add_documents_async(chunk_dicts)
            
            print(f"  [Background] OCR complete for {filename}: {len(chunks)} chunks")
        else:
            print(f"  [Background] No text extracted from {filename}")
            
    except Exception as e:
        print(f"  [Background] OCR failed for {filename}: {e}")


async def process_document_background(file_path: str, filename: str):
    """
    Background task to process document and update vector store.
    This runs after the upload response is sent to the user.
    """
    try:
        print(f"  [Background] Processing document {filename}...")
        
        # Process the document
        chunks = await document_processor.process_document_async(file_path)
        
        if chunks:
            # Delete the placeholder chunk
            vector_store.delete_document(filename)
            
            # Add the real chunks
            chunk_dicts = [chunk.to_dict() for chunk in chunks]
            await vector_store.add_documents_async(chunk_dicts)
            
            print(f"  [Background] Document processed {filename}: {len(chunks)} chunks")
        else:
            print(f"  [Background] No content extracted from {filename}")
            
    except Exception as e:
        print(f"  [Background] Document processing failed for {filename}: {e}")


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
    Streaming chat endpoint with smart search - returns response word-by-word for better UX.
    Uses Server-Sent Events (SSE) format.
    
    Smart Search Logic:
    - DOCUMENTS_ONLY: Questions about specific document content
    - WEB_ONLY: General knowledge questions, definitions, how-tos
    - BOTH: Questions that need document data + web explanation
    """
    print(f"\n{'='*50}")
    print(f"[STREAM] New question: {request.question[:100]}...")
    print(f"{'='*50}")
    
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    
    # Analyze query intent
    analysis = query_analyzer.analyze(request.question)
    intent = analysis["intent"]
    search_mode = intent.value
    
    print(f"  [SmartSearch] Intent: {search_mode}")
    
    # Validate n_chunks
    n_chunks = max(1, min(request.n_chunks, 10))  # Clamp between 1 and 10
    
    chunks = []
    web_results = []
    
    # Search documents if needed
    if analysis["use_docs"]:
        chunks = vector_store.search(
            request.question, 
            n_results=n_chunks,
            filter_sources=request.filter_sources,
            upload_dir=str(UPLOAD_DIR)
        )
        print(f"  [SmartSearch] Found {len(chunks)} document chunks")
    
    # Check if we should fallback to web
    if analysis.get("fallback_to_web") and query_analyzer.should_fallback_to_web(chunks):
        analysis["use_web"] = True
        search_mode = "both"
        print(f"  [SmartSearch] Low doc relevance, adding web search")
    
    # Search web if needed
    if analysis["use_web"]:
        web_results = web_search.search(request.question, num_results=5)
        print(f"  [SmartSearch] Found {len(web_results)} web results")
    
    # Handle case where no results from either source
    if not chunks and not web_results:
        async def no_results_response():
            if request.filter_sources:
                missing_files = []
                for source in request.filter_sources:
                    file_path = UPLOAD_DIR / source
                    if not file_path.exists():
                        missing_files.append(source)
                
                if missing_files:
                    msg = f"📄 **No reference documents found**\n\nThe document(s) you're asking about have been deleted from the system:\n"
                    for f in missing_files[:3]:
                        msg += f"- {f}\n"
                    if len(missing_files) > 3:
                        msg += f"- ...and {len(missing_files) - 3} more\n"
                    msg += "\nPlease upload the documents again or clear this chat to start fresh."
                    yield f"data: {msg}\n\n"
                else:
                    yield "data: 📄 **No relevant information found**\n\nI couldn't find any relevant information to answer this question.\n\n"
            elif intent == SearchIntent.WEB_ONLY:
                yield "data: 🌐 **No web results found**\n\nI couldn't find relevant information on the web for this query.\n\n"
            else:
                yield "data: 📄 **No documents available**\n\nPlease upload some documents first so I can help answer your questions!\n\n"
            yield f"data: [SEARCH_MODE]{search_mode}[/SEARCH_MODE]\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(no_results_response(), media_type="text/event-stream")
    
    # Get unique sources for the response
    sources = list(set(chunk["source"] for chunk in chunks)) if chunks else []
    web_sources = [{"title": r.get("title", ""), "url": r.get("url", "")} for r in web_results[:3]]
    
    import asyncio
    import json
    
    async def generate():
        try:
            # Run sync generator in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            # Create a queue to pass chunks from sync to async
            import queue
            chunk_queue = queue.Queue()
            done_event = asyncio.Event()
            
            def run_sync_generator():
                try:
                    # Use the smart search streaming method
                    for chunk in rag_engine.usf_service.generate_answer_stream_smart(
                        question=request.question,
                        document_chunks=chunks,
                        web_results=web_results,
                        search_mode=search_mode
                    ):
                        chunk_queue.put(chunk)
                    chunk_queue.put(None)  # Signal completion
                except Exception as e:
                    chunk_queue.put(f"[ERROR]{str(e)}[/ERROR]")
                    chunk_queue.put(None)
            
            # Start the sync generator in a thread
            import threading
            thread = threading.Thread(target=run_sync_generator)
            thread.start()
            
            # Yield chunks as they arrive
            while True:
                # Check queue with small timeout to allow async yielding
                try:
                    chunk = chunk_queue.get(timeout=0.01)
                    if chunk is None:
                        break
                    if chunk.startswith("[ERROR]"):
                        yield f"data: {chunk}\n\n"
                        break
                    yield f"data: {chunk}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue
            
            thread.join()
            
            # Send sources at the end (document sources)
            if sources:
                yield f"data: [SOURCES]{','.join(sources)}[/SOURCES]\n\n"
            
            # Send web sources
            if web_sources:
                yield f"data: [WEB_SOURCES]{json.dumps(web_sources)}[/WEB_SOURCES]\n\n"
            
            # Send search mode
            yield f"data: [SEARCH_MODE]{search_mode}[/SEARCH_MODE]\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR]{str(e)}[/ERROR]\n\n"
    
    return StreamingResponse(
        generate(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get statistics about the indexed documents."""
    stats = vector_store.get_stats()
    documents = vector_store.list_documents()
    
    return StatsResponse(
        total_chunks=stats["total_chunks"],
        documents=documents
    )


@app.delete("/documents/all")
async def delete_all_documents():
    """
    Delete ALL documents from the system.
    
    This removes:
    1. All files from uploads directory
    2. All chunks from the vector store
    """
    documents = vector_store.list_documents()
    total_chunks_deleted = 0
    files_deleted = 0
    
    for doc in documents:
        # Delete from vector store
        chunks_deleted = vector_store.delete_document(doc)
        total_chunks_deleted += chunks_deleted
        
        # Delete the file if it exists
        file_path = UPLOAD_DIR / doc
        if file_path.exists():
            file_path.unlink()
            files_deleted += 1
    
    # Also delete any files in uploads that aren't in vector store
    for file_path in UPLOAD_DIR.iterdir():
        if file_path.is_file() and file_path.name not in documents:
            file_path.unlink()
            files_deleted += 1
    
    return {
        "documents_deleted": len(documents),
        "files_deleted": files_deleted,
        "chunks_deleted": total_chunks_deleted
    }


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


# Cache for JSON extraction results
json_cache = {}

@app.get("/json")
async def get_document_json(name: str):
    """
    Extract structured JSON from a document using Vision AI OCR.
    Use query parameter: /json?name=filename.pdf
    Results are cached to avoid re-processing.
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
    
    # Check cache first - use file path and modification time as key
    file_mtime = file_path.stat().st_mtime
    cache_key = f"{filename}_{file_mtime}"
    
    if cache_key in json_cache:
        print(f"  [JSON] Cache hit for {filename}")
        return json_cache[cache_key]
    
    ext = file_path.suffix.lower()
    
    print(f"  [JSON] Extracting from {filename}...")
    
    # For images, extract JSON directly
    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
        json_data = ocr_service.extract_structured_json(str(file_path))
        result = {"filename": filename, "type": "image", "data": json_data}
        json_cache[cache_key] = result  # Cache the result
        return result
    
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
            
            result = {"filename": filename, "type": "pdf", "data": json_data}
            json_cache[cache_key] = result  # Cache the result
            return result
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

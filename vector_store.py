"""
Vector Store Module
===================
This module handles storing and searching document embeddings using ChromaDB.

Key concepts:
- EMBEDDINGS: Text converted to numerical vectors (lists of numbers).
  Similar text = similar vectors = close together in "vector space"

- VECTOR DATABASE: A database optimized for storing vectors and finding
  similar ones quickly. ChromaDB handles this locally (no server needed).

- SIMILARITY SEARCH: Given a query vector, find the most similar stored
  vectors. This is how we find relevant document chunks for a question.
"""

import os
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class VectorStore:
    """
    Manages document embeddings using ChromaDB and Sentence Transformers.
    
    The embedding model runs locally - no API calls needed!
    We use 'all-MiniLM-L6-v2' which is:
    - Fast (small model)
    - Good quality for semantic search
    - Free and runs on CPU
    """
    
    def __init__(self, persist_directory: str = "chroma_data"):
        """
        Initialize the vector store.
        
        Args:
            persist_directory: Where to save the database (survives restarts)
        """
        self.persist_directory = persist_directory
        
        # Create directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB with persistence
        # This means your documents stay saved even after restarting
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # Get or create our collection (like a table in SQL)
        # We'll store all document chunks here
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"description": "RAG document chunks"}
        )
        
        # Initialize the embedding model
        # First run will download the model (~90MB)
        print("Loading embedding model (first time may take a minute)...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Embedding model loaded!")
        
        # Thread pool for async operations
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def add_documents(self, chunks: List[Dict]) -> int:
        """
        Add document chunks to the vector store.
        
        Args:
            chunks: List of dicts with 'content', 'source', 'chunk_index'
        
        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0
        
        # Extract the text content for embedding
        texts = [chunk["content"] for chunk in chunks]
        
        # Generate embeddings for all chunks at once (more efficient)
        # This converts text to vectors using the neural network
        embeddings = self.embedding_model.encode(texts).tolist()
        
        # Prepare data for ChromaDB
        ids = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            # Create unique ID for each chunk
            chunk_id = f"{chunk['source']}_{chunk['chunk_index']}"
            ids.append(chunk_id)
            
            # Store metadata (everything except the content itself)
            # Include upload date for tracking when documents were added
            metadatas.append({
                "source": chunk["source"],
                "chunk_index": chunk["chunk_index"],
                "uploaded_at": chunk.get("uploaded_at", datetime.now().isoformat())
            })
        
        # Add to ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        print(f"  Added {len(chunks)} chunks to vector store")
        return len(chunks)
    
    async def add_documents_async(self, chunks: List[Dict]) -> int:
        """
        Async version of add_documents for parallel processing.
        Runs embedding in thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.add_documents,
            chunks
        )
    
    def search(self, query: str, n_results: int = 5, filter_sources: List[str] = None, upload_dir: str = None) -> List[Dict]:
        """
        Search for document chunks similar to the query.
        
        This is the "Retrieval" part of RAG!
        
        Args:
            query: The user's question
            n_results: How many chunks to return (default 5 for better context)
            filter_sources: Optional list of source filenames to filter results
            upload_dir: Optional path to uploads directory to filter out deleted files
        
        Returns:
            List of relevant chunks with their similarity scores
        """
        from pathlib import Path
        
        # Convert query to embedding
        query_embedding = self.embedding_model.encode(query).tolist()
        
        # If filter_sources provided, verify they still exist on disk
        original_filter_sources = filter_sources.copy() if filter_sources else None
        if filter_sources and upload_dir:
            upload_path = Path(upload_dir)
            existing_sources = [s for s in filter_sources if (upload_path / s).exists()]
            if len(existing_sources) < len(filter_sources):
                deleted = set(filter_sources) - set(existing_sources)
                print(f"  Note: {len(deleted)} file(s) no longer exist: {deleted}")
            
            # If user specified files but none exist, return empty results
            # Don't fall back to searching all documents
            if len(existing_sources) == 0 and original_filter_sources:
                print(f"  All specified files have been deleted. Returning empty results.")
                return []
            
            filter_sources = existing_sources
        
        # Build where clause for filtering by source
        where_clause = None
        if filter_sources and len(filter_sources) > 0:
            if len(filter_sources) == 1:
                where_clause = {"source": filter_sources[0]}
            else:
                where_clause = {"source": {"$in": filter_sources}}
            print(f"  Filtering search to sources: {filter_sources}")
        
        # Search ChromaDB for similar vectors
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results * 2 if upload_dir else n_results,  # Get extra results to filter
            include=["documents", "metadatas", "distances"],
            where=where_clause
        )
        
        # Format results nicely
        formatted_results = []
        
        if results["documents"] and results["documents"][0]:
            for i in range(len(results["documents"][0])):
                source = results["metadatas"][0][i]["source"]
                
                # Skip results from deleted files
                if upload_dir:
                    file_path = Path(upload_dir) / source
                    if not file_path.exists():
                        print(f"  Skipping chunk from deleted file: {source}")
                        continue
                
                formatted_results.append({
                    "content": results["documents"][0][i],
                    "source": source,
                    "chunk_index": results["metadatas"][0][i]["chunk_index"],
                    "uploaded_at": results["metadatas"][0][i].get("uploaded_at", "unknown"),
                    # ChromaDB returns distance (lower = more similar)
                    # Convert to similarity score (higher = more similar)
                    "similarity": 1 - results["distances"][0][i]
                })
                
                # Stop once we have enough results
                if len(formatted_results) >= n_results:
                    break
        
        print(f"  Found {len(formatted_results)} relevant chunks for query")
        
        return formatted_results
    
    def get_stats(self) -> Dict:
        """Get statistics about the vector store."""
        return {
            "total_chunks": self.collection.count(),
            "persist_directory": self.persist_directory
        }
    
    def delete_document(self, source: str) -> int:
        """
        Delete all chunks from a specific document.
        
        Args:
            source: The filename to delete
        
        Returns:
            Number of chunks deleted
        """
        # Find all chunks from this source
        results = self.collection.get(
            where={"source": source},
            include=["metadatas"]
        )
        
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            print(f"Deleted {len(results['ids'])} chunks from '{source}'")
            return len(results["ids"])
        
        return 0
    
    def list_documents(self) -> List[str]:
        """Get a list of all unique document sources."""
        results = self.collection.get(include=["metadatas"])
        
        sources = set()
        for metadata in results["metadatas"]:
            sources.add(metadata["source"])
        
        return sorted(list(sources))


# Quick test if run directly
if __name__ == "__main__":
    # Test the vector store
    store = VectorStore(persist_directory="test_chroma_data")
    
    # Add some test documents
    test_chunks = [
        {"content": "Python is a programming language.", "source": "test.txt", "chunk_index": 0},
        {"content": "Machine learning uses algorithms to learn from data.", "source": "test.txt", "chunk_index": 1},
        {"content": "RAG combines retrieval with generation.", "source": "test.txt", "chunk_index": 2},
    ]
    
    store.add_documents(test_chunks)
    
    # Test search
    results = store.search("What is RAG?")
    print("\nSearch results for 'What is RAG?':")
    for r in results:
        print(f"  - {r['content'][:50]}... (similarity: {r['similarity']:.3f})")
    
    # Show stats
    print(f"\nStats: {store.get_stats()}")

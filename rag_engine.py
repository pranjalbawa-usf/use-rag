"""
RAG Engine Module
=================
This module combines retrieval and generation - the heart of the RAG system!

The flow:
1. User asks a question
2. We search the vector store for relevant chunks
3. We build a prompt with those chunks as context
4. USF model generates an answer based on the context
5. We return the answer along with sources

This is where the magic happens!
"""

import os
from typing import List, Dict, Optional
from dotenv import load_dotenv

from vector_store import VectorStore
from usf_service import USFService

# Load environment variables from .env file
load_dotenv()


class RAGEngine:
    """
    The main RAG engine that orchestrates retrieval and generation.
    
    This class:
    1. Takes user questions
    2. Retrieves relevant context from the vector store
    3. Sends context + question to USF model
    4. Returns USF's answer with source citations
    """
    
    def __init__(self, vector_store: VectorStore):
        """
        Initialize the RAG engine.
        
        Args:
            vector_store: An initialized VectorStore instance
        """
        self.vector_store = vector_store
        
        # Initialize the USF service
        self.usf_service = USFService()
    
    def _build_context(self, chunks: List[Dict]) -> str:
        """
        Build a context string from retrieved chunks.
        
        We format the chunks clearly so the model knows:
        - Which document each chunk came from
        - The actual content of each chunk
        """
        if not chunks:
            return "No relevant documents found."
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(
                f"[Source: {chunk['source']}]\n{chunk['content']}"
            )
        
        return "\n\n---\n\n".join(context_parts)
    
    def query(self, question: str, n_chunks: int = 3, upload_dir: str = None) -> Dict:
        """
        Process a user question and generate an answer.
        
        This is the main method you'll call!
        
        Args:
            question: The user's question
            n_chunks: Number of context chunks to retrieve (default 3)
            upload_dir: Optional path to uploads directory to filter out deleted files
        
        Returns:
            Dict with 'answer', 'sources', and 'chunks_used'
        """
        # Step 1: Retrieve relevant chunks
        print(f"Searching for relevant context...")
        chunks = self.vector_store.search(question, n_results=n_chunks, upload_dir=upload_dir)
        
        if not chunks:
            return {
                "answer": "I don't have any documents to search through yet. Please upload some documents first!",
                "sources": [],
                "chunks_used": []
            }
        
        # Step 2: Generate answer using USF service
        # The USF service handles context building and API calls internally
        answer = self.usf_service.generate_answer(question, chunks)
        
        # Step 3: Prepare the response
        # Get unique sources
        sources = list(set(chunk["source"] for chunk in chunks))
        
        return {
            "answer": answer,
            "sources": sources,
            "chunks_used": chunks
        }
    
    def query_with_history(
        self, 
        question: str, 
        chat_history: List[Dict],
        n_chunks: int = 3
    ) -> Dict:
        """
        Process a question with conversation history for context.
        
        This allows for follow-up questions like "Tell me more about that"
        
        Args:
            question: The current question
            chat_history: List of previous {"role": "user/assistant", "content": "..."}
            n_chunks: Number of context chunks to retrieve
        
        Returns:
            Dict with 'answer', 'sources', and 'chunks_used'
        """
        # Retrieve relevant chunks
        chunks = self.vector_store.search(question, n_results=n_chunks)
        
        # Generate answer using USF service with history
        answer = self.usf_service.generate_with_history(question, chunks, chat_history)
        
        sources = list(set(chunk["source"] for chunk in chunks))
        
        return {
            "answer": answer,
            "sources": sources,
            "chunks_used": chunks
        }


# Quick test if run directly
if __name__ == "__main__":
    # This requires documents to be already added to the vector store
    store = VectorStore()
    engine = RAGEngine(store)
    
    # Test query
    result = engine.query("What documents do you have?")
    print(f"\nAnswer: {result['answer']}")
    print(f"Sources: {result['sources']}")

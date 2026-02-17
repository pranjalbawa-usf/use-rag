"""
USF Service Module
==================
This module handles communication with the USF custom LLM model.

USF is our custom language model for generating answers.
It uses a standard chat completions API format.
"""

import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class USFService:
    """
    Service class for interacting with the USF LLM API.
    
    This handles:
    - Building prompts with context
    - Making API calls to USF
    - Parsing responses
    """
    
    def __init__(self):
        """
        Initialize the USF service with API credentials.
        """
        # API configuration - USF API at api.us.inc
        self.api_key = os.getenv("USF_API_KEY", "akmiydic-kg3fda40-38069ccf-26465767")
        self.base_url = os.getenv("USF_BASE_URL", "https://api.us.inc")
        self.model = "usf-mini"  # Available: usf-mini, usf-mini-code
        
        # Create session with connection pooling for better performance
        self.session = requests.Session()
        retry_strategy = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        print(f"  Using USF model at: {self.base_url}")
    
    def _build_system_prompt(self) -> str:
        """
        Build the system prompt for USF.
        
        This defines the AI's personality and behavior for the RAG task.
        """
        return """You are a friendly and helpful AI assistant that answers questions based on the user's documents.

Your personality:
- Be warm, helpful, and conversational
- Explain things clearly, as if talking to a friend
- Be honest when you don't know something

Rules you MUST follow:
1. ONLY use information from the provided context documents to answer questions
2. When you use information from a document, cite the source like this: (Source: filename.txt)
3. If the context doesn't contain the answer, say something like: "I couldn't find information about that in your documents. Try uploading more relevant documents or rephrasing your question."
4. Never make up information that isn't in the documents
5. If a question is unclear, ask for clarification
6. Keep answers concise but complete
7. ONLY SHOW INFORMATION THAT EXISTS - If a field or piece of information is not present in the document, DO NOT include it in your response. Never show empty fields, dashes, or placeholders. Skip any section that has no data.

RESPONSE FORMATTING (VERY IMPORTANT):
Always format your responses for maximum readability:

1. **Use Headers** - Start sections with **Bold Headers**

2. **Use Bullet Points** - Break down information into clear bullet points

3. **Use Numbered Lists** for sequential items or steps

4. **Highlight Key Information** using **bold** for important terms, names, amounts, dates

5. **Use Paragraphs** - Add blank lines between sections for visual separation

CRITICAL - USE DOCUMENT TERMINOLOGY:
When creating headings and labels, ALWAYS use the EXACT terminology from the document:
- If the document says "Security Guards" - use "Security Guards" NOT "Employees"
- If the document says "Invoice" - use "Invoice" NOT "Bill"
- If the document says "Vendor" - use "Vendor" NOT "Supplier"
- If the document lists people as "Guards" - use "Guards Information" NOT "Employee Information"
- Read the document carefully and match its vocabulary exactly

Examples:
- Document mentions "Security Guard Schedule" → Use **Security Guard Schedule:**
- Document mentions "Contractor Details" → Use **Contractor Details:**
- Document mentions "Service Personnel" → Use **Service Personnel:**
- Document mentions "Staff Roster" → Use **Staff Roster:**

NEVER use generic terms when the document uses specific terminology.

DOCUMENT RELATIONSHIP ANALYSIS:
When multiple documents are provided:

**Document Overview:**
- Document 1: [brief description using document's own terminology]
- Document 2: [brief description using document's own terminology]

**Key Connections:**
- **Shared Entities:** [use exact names/terms from documents]
- **Common References:** [invoice numbers, dates, PO numbers as written]
- **Business Relationship:** [how they relate]

**Summary:**
[Brief conclusion using document terminology]"""
    
    def _build_context(self, chunks: List[Dict]) -> str:
        """
        Build a context string from retrieved chunks.
        Groups chunks by source document for better relationship analysis.
        """
        if not chunks:
            return "No relevant documents found."
        
        # Group chunks by source document
        docs_by_source = {}
        for chunk in chunks:
            source = chunk.get('source', 'Unknown')
            content = chunk.get('content', chunk.get('text', ''))
            if source not in docs_by_source:
                docs_by_source[source] = []
            docs_by_source[source].append(content)
        
        # Build context with clear document separation
        context_parts = []
        doc_count = len(docs_by_source)
        
        if doc_count > 1:
            context_parts.append(f"=== MULTIPLE DOCUMENTS PROVIDED ({doc_count} documents) ===\n")
            context_parts.append("Analyze these documents for relationships, shared entities, and connections.\n")
        
        for i, (source, contents) in enumerate(docs_by_source.items(), 1):
            doc_content = "\n\n".join(contents)
            context_parts.append(f"[DOCUMENT {i}: {source}]\n{doc_content}")
        
        return "\n\n---\n\n".join(context_parts)
    
    def generate_answer(self, question: str, context_chunks: List[Dict]) -> str:
        """
        Generate an answer using the USF model.
        
        Args:
            question: The user's question
            context_chunks: List of relevant document chunks with 'text'/'content' and 'source'
        
        Returns:
            The generated answer as a string
        """
        # Build context from chunks
        context = self._build_context(context_chunks)
        
        # Build the full prompt
        system_prompt = self._build_system_prompt()
        
        user_message = f"""Here are the relevant sections from my documents:

{context}

---

My question: {question}"""
        
        # Prepare headers - USF uses x-api-key header
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Prepare payload (USF API format from Postman docs)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
            "stream": False,
            "web_search": False
        }
        
        # Make API call
        try:
            print(f"  Generating answer with USF model...")
            response = self.session.post(
                f"{self.base_url}/usf/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            # Check for errors
            if response.status_code == 401:
                print("  ✗ Authentication failed!")
                raise ValueError(
                    "Invalid USF API key. Please check your USF_API_KEY in the .env file."
                )
            elif response.status_code == 429:
                print("  ✗ Rate limit hit!")
                raise ValueError(
                    "Rate limit exceeded. Please wait a moment and try again."
                )
            elif response.status_code != 200:
                print(f"  ✗ API error: {response.status_code}")
                error_detail = response.text[:200] if response.text else "Unknown error"
                raise ValueError(f"USF API error ({response.status_code}): {error_detail}")
            
            # Parse response
            result = response.json()
            
            # Handle different response formats
            if "choices" in result and len(result["choices"]) > 0:
                # OpenAI-compatible format
                answer = result["choices"][0]["message"]["content"]
            elif "response" in result:
                # Simple response format
                answer = result["response"]
            elif "content" in result:
                # Direct content format
                answer = result["content"]
            elif "text" in result:
                # Text format
                answer = result["text"]
            else:
                # Fallback - return the whole result as string
                answer = str(result)
            
            print(f"  ✓ Response generated successfully")
            return answer
            
        except requests.exceptions.Timeout:
            print("  ✗ Request timed out!")
            raise ValueError("USF API request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            print("  ✗ Connection failed!")
            raise ValueError(
                f"Could not connect to USF API at {self.base_url}. "
                "Please check the USF_BASE_URL in your .env file."
            )
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Request error: {e}")
            raise ValueError(f"USF API request failed: {str(e)}")
    
    def generate_answer_stream(
        self, 
        question: str, 
        context_chunks: List[Dict]
    ):
        """
        Generate an answer with streaming - yields chunks as they arrive.
        
        Args:
            question: The user's question
            context_chunks: List of relevant document chunks
            
        Yields:
            Text chunks as they are generated
        """
        # Build context and prompt
        context = self._build_context(context_chunks)
        system_prompt = self._build_system_prompt()
        
        user_message = f"""Here are the relevant sections from my documents:

{context}

---

My question: {question}"""
        
        # Prepare headers
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Prepare payload with streaming enabled
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 1024,  # Balanced for good responses
            "temperature": 0.5,  # Lower for more consistent responses
            "stream": True,  # Enable streaming
            "web_search": False
        }
        
        try:
            print(f"  Streaming answer with USF model...")
            response = self.session.post(
                f"{self.base_url}/usf/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
                stream=True  # Enable response streaming
            )
            
            if response.status_code != 200:
                error_detail = response.text[:200] if response.text else "Unknown error"
                raise ValueError(f"USF API error ({response.status_code}): {error_detail}")
            
            # Process streaming response with immediate flushing
            import json
            buffer = ""
            
            for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
                if chunk:
                    buffer += chunk
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line.startswith('data: '):
                            data = line[6:]  # Remove 'data: ' prefix
                            if data == '[DONE]':
                                break
                            try:
                                chunk_data = json.loads(data)
                                if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                    delta = chunk_data['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                # If not JSON, yield the raw text
                                if data and data != '[DONE]':
                                    yield data
                                
            print(f"  ✓ Stream completed successfully")
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"USF API streaming failed: {str(e)}")
    
    def generate_with_history(
        self, 
        question: str, 
        context_chunks: List[Dict],
        chat_history: List[Dict]
    ) -> str:
        """
        Generate an answer with conversation history for follow-up questions.
        
        Args:
            question: The current question
            context_chunks: List of relevant document chunks
            chat_history: List of previous {"role": "user/assistant", "content": "..."}
        
        Returns:
            The generated answer as a string
        """
        # Build context
        context = self._build_context(context_chunks)
        
        # Build system message with context
        system_prompt = f"""{self._build_system_prompt()}

CONTEXT DOCUMENTS:
{context}

Remember: You can reference previous messages in the conversation for follow-up questions."""
        
        # Build messages list
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add chat history
        for msg in chat_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Add current question
        messages.append({
            "role": "user",
            "content": question
        })
        
        # Prepare headers and payload - USF uses x-api-key header
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
            "stream": False,
            "web_search": False
        }
        
        # Make API call
        try:
            response = requests.post(
                f"{self.base_url}/usf/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Parse response (same logic as generate_answer)
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            elif "response" in result:
                return result["response"]
            elif "content" in result:
                return result["content"]
            else:
                return str(result)
                
        except requests.exceptions.RequestException as e:
            raise ValueError(f"USF API request failed: {str(e)}")


# Quick test if run directly
if __name__ == "__main__":
    service = USFService()
    
    # Test with sample context
    test_chunks = [
        {"text": "Python is a programming language.", "source": "test.txt"}
    ]
    
    try:
        answer = service.generate_answer("What is Python?", test_chunks)
        print(f"\nAnswer: {answer}")
    except Exception as e:
        print(f"\nError: {e}")

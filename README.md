# USF RAG System 🤖

A Retrieval-Augmented Generation (RAG) chatbot that lets you chat with your documents using USF AI. Features a sleek modern interface with drag-and-drop uploads!

---

## 🎯 What is RAG?

RAG combines two powerful techniques:
1. **Retrieval**: Finding relevant information from your documents
2. **Generation**: Using an LLM (USF) to generate natural answers based on that information

This means the AI can answer questions about YOUR documents, not just its training data!

### How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Upload     │────▶│  Split into  │────▶│  Convert to │
│  Document   │     │   Chunks     │     │  Embeddings │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  USF Model  │◀────│  Retrieve    │◀────│  Store in   │
│  Generates  │     │  Top 5       │     │  ChromaDB   │
│  Answer     │     │  Chunks      │     └─────────────┘
└─────────────┘     └──────────────┘
```

---

## 🚀 Quick Start

### Step 1: Set Up Python Environment

```bash
# Navigate to project folder
cd "/Users/pranjalbawa/Desktop/my first rag"

# Create a virtual environment (isolates dependencies)
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
# On Windows use: venv\Scripts\activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- **FastAPI** + **Uvicorn**: Web server
- **ChromaDB**: Vector database
- **Sentence-Transformers**: Creates embeddings locally
- **Requests**: HTTP client for USF API
- **PyPDF**: PDF text extraction

> ⏱️ First run downloads the embedding model (~90MB). This only happens once!

### Step 3: Add Your API Key

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your key
nano .env   # or use any text editor
```

Your `.env` file should look like:
```
USF_API_KEY=akmiydic-kg3fda40-38069ccf-26465767
```

The USF API key is pre-configured in .env.example

### Step 4: Run the Server

```bash
python main.py
```

You should see:
```
==================================================
Initializing RAG System...
==================================================
Loading embedding model (first time may take a minute)...
Embedding model loaded!
  Using USF model at: https://usf-api.omega-healthcare.ai
==================================================
RAG System Ready!
==================================================

Starting RAG Server...
Open http://localhost:8000 in your browser
```

### Step 5: Open in Browser

Go to **http://localhost:8000**

You'll see a dark-themed chat interface. Try:
1. Drag & drop a document onto the upload area
2. Ask a question about your document
3. See the AI response with source citations!

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📄 **Multi-format Upload** | Supports TXT, PDF, and Markdown files |
| 🎯 **Drag & Drop** | Just drag files onto the upload area |
| 🔍 **Semantic Search** | Finds relevant content by meaning, not just keywords |
| 📊 **Top 5 Chunks** | Retrieves the 5 most relevant document sections |
| 🤖 **USF Integration** | Uses USF model for natural answers |
| 📚 **Source Citations** | Shows which documents were used for each answer |
| 🌙 **Dark Mode UI** | Modern, easy-on-the-eyes interface |
| 📱 **Responsive** | Works on desktop and mobile |
| 💾 **Persistent Storage** | Documents survive server restarts |

---

## 📁 Project Structure

```
my first rag/
├── main.py                 # FastAPI server & API endpoints
├── document_processor.py   # Loads docs, splits into chunks
├── vector_store.py         # ChromaDB + embedding operations
├── rag_engine.py           # Combines retrieval + USF generation
├── requirements.txt        # Python dependencies
├── .env.example            # Template for API key
├── .env                    # Your API key (create this!)
├── .gitignore              # Excludes sensitive files from git
├── static/
│   ├── index.html          # Web interface structure
│   ├── style.css           # Dark mode styling
│   └── app.js              # Frontend JavaScript
├── sample_documents/       # Example documents to try
│   ├── about_rag.txt
│   └── python_tips.md
├── uploads/                # Uploaded documents (auto-created)
└── chroma_data/            # Vector database (auto-created)
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the web interface |
| `POST` | `/upload` | Upload a document (multipart form) |
| `POST` | `/chat` | Ask a question, get an answer |
| `GET` | `/documents` | List all uploaded documents |
| `DELETE` | `/document/{filename}` | Delete a document |
| `GET` | `/stats` | Get system statistics |
| `GET` | `/health` | Health check endpoint |

### Example: Chat API

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is RAG?", "n_chunks": 5}'
```

Response:
```json
{
  "answer": "RAG stands for Retrieval-Augmented Generation...",
  "sources": ["about_rag.txt"],
  "chunks_used": [...]
}
```

---

## 🧠 How Each Component Works

### 1. Document Processor (`document_processor.py`)
- Loads TXT, MD, and PDF files
- Splits text into ~500 character chunks with 50 char overlap
- Overlap ensures context isn't lost at chunk boundaries

### 2. Vector Store (`vector_store.py`)
- Uses `all-MiniLM-L6-v2` model to create embeddings (runs locally!)
- Stores embeddings in ChromaDB (persisted to disk)
- Searches by cosine similarity to find relevant chunks

### 3. RAG Engine (`rag_engine.py`)
- Retrieves top 5 most similar chunks for a query
- Builds a prompt with context + question
- Calls USF API with a system prompt that:
  - Instructs the model to only use provided context
  - Requires source citations
  - Handles "I don't know" gracefully

### 4. FastAPI Backend (`main.py`)
- Serves the web interface
- Handles file uploads and processing
- Provides REST API for chat and document management
- Includes CORS for development flexibility

---

## 🛠️ Troubleshooting

### "USF API connection failed"
Make sure you created `.env` file with your API settings:
```bash
cp .env.example .env
# The API key is pre-configured
```

### "Rate limit exceeded"
Wait a moment and try again.

### "Module not found" errors
Make sure your virtual environment is activated:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Embedding model download stuck
First run downloads ~90MB model. Check your internet connection.

---

## 📚 Sample Documents

The `sample_documents/` folder contains example files to test with:
- `about_rag.txt` - Explains RAG concepts
- `python_tips.md` - Python best practices

Upload these to test the system!

---

## 🔧 Tech Stack

| Component | Technology | Why? |
|-----------|------------|------|
| Backend | FastAPI | Modern, fast, automatic API docs |
| Vector DB | ChromaDB | Free, local, no server needed |
| Embeddings | Sentence Transformers | Free, runs locally on CPU |
| LLM | USF Model | Fast, high quality |
| Frontend | Vanilla JS | Simple, no build step needed |

---

## 💡 Tips for Best Results

1. **Upload relevant documents** - The more focused your docs, the better the answers
2. **Ask specific questions** - "What are the benefits of RAG?" works better than "Tell me stuff"
3. **Check the sources** - See which documents were used to verify accuracy
4. **Upload multiple docs** - Build a knowledge base on a topic

---

## 🎓 Learning Resources

Want to understand RAG better? Here's what each concept means:

- **Embeddings**: Converting text to numbers that capture meaning
- **Vector Database**: A database optimized for finding similar vectors
- **Chunking**: Splitting documents into smaller pieces for better retrieval
- **Semantic Search**: Finding content by meaning, not exact word matches
- **Context Window**: The amount of text an LLM can process at once

---

Built with ❤️ using FastAPI, ChromaDB, Sentence Transformers, and USF AI

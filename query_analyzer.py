"""
Query Analyzer for Smart Search Intent Detection
=================================================
Analyzes user queries to determine whether to search documents, web, or both.
"""

import re
from enum import Enum
from typing import Dict, List, Optional


class SearchIntent(Enum):
    DOCUMENTS_ONLY = "documents_only"
    WEB_ONLY = "web_only"
    BOTH = "both"
    NO_DOCUMENTS = "no_documents"
    NEED_CLARIFICATION = "need_clarification"
    GREETING = "greeting"
    IDENTITY = "identity"  # "Who built you?", "Are you ChatGPT?"
    CAPABILITIES = "capabilities"  # "What can you do?", "What are your features?"
    COMPARISON = "comparison"  # "Are you better than ChatGPT?"


class QueryAnalyzer:
    """
    Analyzes queries to determine search intent.
    
    Intent Detection:
    - DOCUMENTS_ONLY: Questions about specific document content
    - WEB_ONLY: General knowledge questions, definitions, how-tos
    - BOTH: Questions that need document data + web explanation
    - NO_DOCUMENTS: User asking about docs but none uploaded
    - NEED_CLARIFICATION: Ambiguous query needs more context
    """
    
    # DOCUMENT queries - these MUST search documents, NEVER web
    DOC_PATTERNS = [
        r'\b(the|my|this|these|uploaded|attached)\s*(document|documents|doc|docs|file|files|pdf|pdfs|report|reports)\b',
        r'\b(document|documents|doc|docs|file|files|pdf|pdfs)\b',
        r'\b(tell|show|give|read)\s*(me)?\s*(about)?\s*(the|my|this)?\s*(doc|docs|document|documents|file|files)\b',
        r'\b(summarize|summary|summarise)\s*(the|my|this)?\s*(doc|docs|document|documents|file|files)?\b',
        r'\b(in|from|according to)\s+(the|my|this)\s+(document|file|pdf|report)\b',
        r'\bwhat\s+(does|did)\s+(the|my|this)\s+(document|file|report)\s+(say|mention|contain)\b',
        r'\b(invoice|receipt|contract|order|po)\s*(number|#|no|date|amount|total)\b',
        r'\b(total|amount|price|quantity|number|value)\s+(in|from|on)\s+(the|my|this)\b',
        r'\babout\s+(the|my|this|these)\s*(doc|docs|document|documents|file|files|pdf|upload|uploaded)\b',
    ]
    
    # GENERAL KNOWLEDGE - should use WEB, NOT documents
    GENERAL_PATTERNS = [
        r'\bwhen\s+(is|was|does|did|will)\s+\w+\s+(start|end|begin|happen)\b',
        r'\b(ramadan|eid|christmas|easter|diwali|hanukkah|thanksgiving)\b',
        r'^what\s+is\s+(a|an|the)?\s*[a-z]+\s*\??$',
        r'^what\s+does\s+[a-z]+\s+mean',
        r'^define\s+[a-z]+',
        r'^how\s+do\s+(i|you|we)\s+',
        r'^how\s+to\s+',
        r'^who\s+(is|was|are)\s+',
        r'^where\s+(is|are|was)\s+',
        r'\b(capital|president|ceo|founder|population)\s+of\b',
        r'\b(latest|current|recent|today|news)\s+\w+',
        r'\b(weather|stock price|score)\s+(in|today|now)\b',
    ]
    
    # AMBIGUOUS queries that need context
    AMBIGUOUS_PATTERNS = [
        r'^tell\s+me\s+about\s+(this|it)\s*\??$',
        r'^what\s+is\s+(this|it)\s*\??$',
        r'^explain\s+(this|it)\s*\??$',
        r'^(this|it)\s*\??$',
    ]
    
    # Patterns that indicate need for both sources
    BOTH_PATTERNS = [
        r'what\s+does\s+(the|this).*\s+(in|from)\s+(my|the)\s+(document|file).*mean',
        r'explain\s+(the|this).*\s+(in|from)\s+(my|the)\s+(document|file)',
    ]
    
    # GREETING/CASUAL patterns - should NOT search anything, just respond friendly
    GREETING_PATTERNS = [
        r'^(hey|hi|hello|hiya|howdy|yo|sup|hola|greetings)[\s\!\?\.\,]*$',
        r'^(hey|hi|hello)\s+(there|you|buddy|friend)[\s\!\?\.\,]*$',
        r'^good\s+(morning|afternoon|evening|day)[\s\!\?\.\,]*$',
        r'^(what\'?s?\s+up|wassup|whats\s+up)[\s\!\?\.\,]*$',
        r'^(how\s+are\s+you|how\'?s\s+it\s+going|how\s+do\s+you\s+do)[\s\!\?\.\,]*$',
        r'^(thanks|thank\s+you|thx|ty)[\s\!\?\.\,]*$',
        r'^(bye|goodbye|see\s+you|later|cya)[\s\!\?\.\,]*$',
        r'^(ok|okay|sure|alright|got\s+it|cool|nice|great|awesome)[\s\!\?\.\,]*$',
    ]
    
    # IDENTITY patterns - "Who built you?", "Are you ChatGPT?"
    IDENTITY_PATTERNS = [
        r'\b(are\s+you|r\s+u)\s+(chatgpt|chat\s*gpt|gpt|openai|claude|anthropic|gemini|google|bard|copilot|bing)',
        r'\b(built|made|created|developed)\s+(by|with)\s+(openai|anthropic|google|microsoft|chatgpt|claude)',
        r'\bwho\s+(built|made|created|developed)\s+you',
        r'\bwhat\s+(are|r)\s+you\s*(built|made|powered)\s*(by|with|on)',
        r'\bare\s+you\s+(gpt|gpt-4|gpt-3|gpt4|chatgpt-4)',
        r'\bwho\s+(are|r)\s+you\s*\??$',
        r'\bwhat\s+ai\s+(are|r)\s+you',
        r'\bwhich\s+(ai|model|llm)\s+(are|r)\s+you',
    ]
    
    # CAPABILITIES patterns - "What can you do?", "What are your features?"
    CAPABILITIES_PATTERNS = [
        r'\bwhat\s+(can|do)\s+you\s+do',
        r'\bwhat\s+are\s+(your|you)\s+(features|capabilities|abilities|functions)',
        r'\bhow\s+can\s+you\s+help',
        r'\bwhat\s+are\s+you\s+capable\s+of',
        r'\bwhat\'?s?\s+your\s+purpose',
        r'\btell\s+me\s+what\s+you\s+(can\s+)?do',
        r'\bwhat\s+do\s+you\s+do',
        r'\bwhat\s+can\s+i\s+(do|ask)\s+(with|you)',
    ]
    
    # COMPARISON patterns - "Are you better than ChatGPT?"
    COMPARISON_PATTERNS = [
        r'\b(are|r)\s+(you|u)\s+(better|smarter|faster|worse)\s+than\s+(chatgpt|claude|claud|gemini|gpt|bard|copilot)',
        r'\b(chatgpt|claude|claud|gemini|gpt|bard|copilot)\s+(vs|versus|or)\s+(you|u)',
        r'\b(you|u)\s+(vs|versus|or)\s+(chatgpt|claude|claud|gemini|gpt|bard|copilot)',
        r'\bhow\s+do\s+(you|u)\s+compare\s+to\s+(chatgpt|claude|claud|gemini|gpt)',
        r'\bwhich\s+is\s+better.*(you|u|chatgpt|claude|claud|gemini)',
        r'\b(are|r)\s+(you|u)\s+the\s+best\s+(ai|assistant|chatbot)',
        r'\bwho\s+(is|s)\s+better.*(you|u).*(chatgpt|claude|claud|gemini|gpt)',
        r'\bwho\s+(is|s)\s+better.*(chatgpt|claude|claud|gemini|gpt).*(you|u)',
        r'\b(better|best).*(you|u).*(or|vs|versus).*(chatgpt|claude|claud|gemini)',
        r'\b(better|best).*(chatgpt|claude|claud|gemini).*(or|vs|versus).*(you|u)',
    ]
    
    def __init__(self):
        self.doc_patterns = [re.compile(p, re.IGNORECASE) for p in self.DOC_PATTERNS]
        self.general_patterns = [re.compile(p, re.IGNORECASE) for p in self.GENERAL_PATTERNS]
        self.ambiguous_patterns = [re.compile(p, re.IGNORECASE) for p in self.AMBIGUOUS_PATTERNS]
        self.both_patterns = [re.compile(p, re.IGNORECASE) for p in self.BOTH_PATTERNS]
        self.greeting_patterns = [re.compile(p, re.IGNORECASE) for p in self.GREETING_PATTERNS]
        self.identity_patterns = [re.compile(p, re.IGNORECASE) for p in self.IDENTITY_PATTERNS]
        self.capabilities_patterns = [re.compile(p, re.IGNORECASE) for p in self.CAPABILITIES_PATTERNS]
        self.comparison_patterns = [re.compile(p, re.IGNORECASE) for p in self.COMPARISON_PATTERNS]
    
    def analyze(self, query: str, has_documents: bool = True) -> Dict:
        """
        Analyze a query to determine search intent.
        
        Args:
            query: The user's question
            has_documents: Whether user has uploaded any documents
            
        Returns:
            Dict with intent, use_docs, use_web, is_general, message
        """
        q = query.lower().strip()
        
        # FIRST: Check for special intents (identity, capabilities, comparison, greeting)
        
        # Check IDENTITY questions - "Are you ChatGPT?", "Who built you?"
        is_identity = any(p.search(q) for p in self.identity_patterns)
        if is_identity:
            print(f"  [QueryAnalyzer] Intent: IDENTITY (who built you question)")
            return {
                "intent": SearchIntent.IDENTITY,
                "use_docs": False,
                "use_web": False,
                "is_general": False,
                "message": None
            }
        
        # Check CAPABILITIES questions - "What can you do?"
        is_capabilities = any(p.search(q) for p in self.capabilities_patterns)
        if is_capabilities:
            print(f"  [QueryAnalyzer] Intent: CAPABILITIES (what can you do question)")
            return {
                "intent": SearchIntent.CAPABILITIES,
                "use_docs": False,
                "use_web": False,
                "is_general": False,
                "message": None
            }
        
        # Check COMPARISON questions - "Are you better than ChatGPT?"
        is_comparison = any(p.search(q) for p in self.comparison_patterns)
        if is_comparison:
            print(f"  [QueryAnalyzer] Intent: COMPARISON (comparison question)")
            return {
                "intent": SearchIntent.COMPARISON,
                "use_docs": False,
                "use_web": False,
                "is_general": False,
                "message": None
            }
        
        # Check if it's a greeting/casual message
        is_greeting = any(p.search(q) for p in self.greeting_patterns)
        if is_greeting:
            print(f"  [QueryAnalyzer] Intent: GREETING (casual message)")
            return {
                "intent": SearchIntent.GREETING,
                "use_docs": False,
                "use_web": False,
                "is_general": False,
                "message": None
            }
        
        # Check if query is ambiguous (like "tell me about this")
        is_ambiguous = any(p.search(q) for p in self.ambiguous_patterns)
        
        # Check if query is about documents
        is_doc_query = any(p.search(q) for p in self.doc_patterns)
        
        # Check if query is general knowledge
        is_general = any(p.search(q) for p in self.general_patterns)
        
        # Check BOTH patterns first (most specific)
        for pattern in self.both_patterns:
            if pattern.search(q):
                print(f"  [QueryAnalyzer] Intent: BOTH (matched hybrid pattern)")
                return {
                    "intent": SearchIntent.BOTH,
                    "use_docs": True,
                    "use_web": True,
                    "is_general": False,
                    "message": None
                }
        
        # CASE 1: Query explicitly about documents
        if is_doc_query:
            if has_documents:
                print(f"  [QueryAnalyzer] Intent: DOCUMENTS_ONLY (doc query, has docs)")
                return {
                    "intent": SearchIntent.DOCUMENTS_ONLY,
                    "use_docs": True,
                    "use_web": False,
                    "is_general": False,
                    "message": None
                }
            else:
                print(f"  [QueryAnalyzer] Intent: NO_DOCUMENTS (doc query, no docs)")
                return {
                    "intent": SearchIntent.NO_DOCUMENTS,
                    "use_docs": False,
                    "use_web": False,
                    "is_general": False,
                    "message": "No documents uploaded yet. Please upload a document first, then ask me about it!"
                }
        
        # CASE 2: Ambiguous query like "tell me about this"
        if is_ambiguous:
            if has_documents:
                print(f"  [QueryAnalyzer] Intent: DOCUMENTS_ONLY (ambiguous, has docs)")
                return {
                    "intent": SearchIntent.DOCUMENTS_ONLY,
                    "use_docs": True,
                    "use_web": False,
                    "is_general": False,
                    "message": None
                }
            else:
                print(f"  [QueryAnalyzer] Intent: NEED_CLARIFICATION (ambiguous, no docs)")
                return {
                    "intent": SearchIntent.NEED_CLARIFICATION,
                    "use_docs": False,
                    "use_web": False,
                    "is_general": False,
                    "message": "I'm not sure what you'd like to know about. Please upload a document and ask me about it, or ask a specific question!"
                }
        
        # CASE 3: General knowledge question
        if is_general and not is_doc_query:
            print(f"  [QueryAnalyzer] Intent: WEB_ONLY (general knowledge)")
            return {
                "intent": SearchIntent.WEB_ONLY,
                "use_docs": False,
                "use_web": True,
                "is_general": True,
                "message": None
            }
        
        # CASE 4: Default - try documents first if they exist
        if has_documents:
            print(f"  [QueryAnalyzer] Intent: DOCUMENTS_ONLY (default, has docs)")
            return {
                "intent": SearchIntent.DOCUMENTS_ONLY,
                "use_docs": True,
                "use_web": False,
                "is_general": False,
                "fallback_to_web": True,
                "message": None
            }
        else:
            # No documents, not clearly general knowledge
            print(f"  [QueryAnalyzer] Intent: NEED_CLARIFICATION (default, no docs)")
            return {
                "intent": SearchIntent.NEED_CLARIFICATION,
                "use_docs": False,
                "use_web": False,
                "is_general": False,
                "message": "I don't have any documents to search. Please upload a document, or ask a general knowledge question (and enable web search)."
            }
    
    def should_fallback_to_web(self, results: List[Dict], threshold: float = 0.4) -> bool:
        """
        Determine if we should fallback to web search based on document results.
        
        Args:
            results: List of document search results
            threshold: Minimum score to consider results good enough
            
        Returns:
            True if web fallback should be used
        """
        if not results:
            return True
        
        # Check if top result has good enough score
        top_score = results[0].get("score", 0) if results else 0
        
        if top_score < threshold:
            print(f"  [QueryAnalyzer] Low doc score ({top_score:.2f}), suggesting web fallback")
            return True
        
        return False

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


class QueryAnalyzer:
    """
    Analyzes queries to determine search intent.
    
    Intent Detection:
    - DOCUMENTS_ONLY: Questions about specific document content
    - WEB_ONLY: General knowledge questions, definitions, how-tos
    - BOTH: Questions that need document data + web explanation
    """
    
    # Patterns that indicate document-specific queries
    DOC_PATTERNS = [
        r'\b(my|this|the|uploaded)\s+(document|file|pdf|report|invoice|receipt|contract)\b',
        r'\b(in|from)\s+(the|this|my)\s+(document|file|pdf|report)\b',
        r'\b(summarize|summary)\s+(this|the|my)\b',
        r'\bthe\s+(total|amount|number|date|name|value|invoice|order|item)\b',
        r'\b(invoice|receipt|contract|order)\s*(number|#|date|amount|total)\b',
        r'\bshow\s+me.*\b(from|in)\s+(my|the)\b',
        r'\bwhat\s+(is|are)\s+the\s+\w+\s+(in|from|on)\b',
        r'\b(extract|find|get|show)\s+(the|all|my)\b',
        r'\baccording\s+to\s+(the|my|this)\s+(document|file)\b',
        r'\b(my|the)\s+(uploaded|attached)\b',
    ]
    
    # Patterns that indicate web/general knowledge queries
    WEB_PATTERNS = [
        r'^what\s+is\s+(a|an)\s+\w+\??$',
        r'^what\s+does\s+\w+\s+mean',
        r'^define\s+',
        r'^how\s+do\s+(i|you|we)\s+',
        r'^how\s+to\s+',
        r'\b(latest|current|recent|news|today|2024|2025|2026)\b',
        r'^who\s+(is|was|are)\s+',
        r'^when\s+(did|was|is|will)\s+',
        r'^where\s+(is|are|can)\s+',
        r'^why\s+(do|does|is|are)\s+',
        r'\b(explain|definition|meaning)\s+of\b',
        r'\b(generally|typically|usually|normally)\b',
        r'^tell\s+me\s+about\s+',
    ]
    
    # Patterns that indicate need for both sources
    BOTH_PATTERNS = [
        r'what\s+does.*\s+(in|from)\s+(my|the|this)\s+(document|file).*mean',
        r'explain.*\s+(in|from)\s+(my|the)\s+(document|file)',
        r'(compare|contrast).*\s+(with|to)\s+(general|standard|typical)',
        r'\b(term|phrase|word)\s+(in|from)\s+(my|the)\s+(document|file)\b',
        r'what\s+does\s+this\s+(term|phrase|word)\s+mean',
    ]
    
    def __init__(self):
        self.doc_patterns = [re.compile(p, re.IGNORECASE) for p in self.DOC_PATTERNS]
        self.web_patterns = [re.compile(p, re.IGNORECASE) for p in self.WEB_PATTERNS]
        self.both_patterns = [re.compile(p, re.IGNORECASE) for p in self.BOTH_PATTERNS]
    
    def analyze(self, query: str) -> Dict:
        """
        Analyze a query to determine search intent.
        
        Args:
            query: The user's question
            
        Returns:
            Dict with intent, use_docs, use_web, and optional fallback_to_web
        """
        q = query.lower().strip()
        
        # Check BOTH patterns first (most specific)
        for pattern in self.both_patterns:
            if pattern.search(q):
                print(f"  [QueryAnalyzer] Intent: BOTH (matched both pattern)")
                return {
                    "intent": SearchIntent.BOTH,
                    "use_docs": True,
                    "use_web": True
                }
        
        # Score document and web patterns
        doc_score = sum(1 for p in self.doc_patterns if p.search(q))
        web_score = sum(1 for p in self.web_patterns if p.search(q))
        
        # Clear document intent
        if doc_score > 0 and web_score == 0:
            print(f"  [QueryAnalyzer] Intent: DOCUMENTS_ONLY (doc_score={doc_score})")
            return {
                "intent": SearchIntent.DOCUMENTS_ONLY,
                "use_docs": True,
                "use_web": False
            }
        
        # Clear web intent
        if web_score > 0 and doc_score == 0:
            print(f"  [QueryAnalyzer] Intent: WEB_ONLY (web_score={web_score})")
            return {
                "intent": SearchIntent.WEB_ONLY,
                "use_docs": False,
                "use_web": True
            }
        
        # Both have scores - use both
        if doc_score > 0 and web_score > 0:
            print(f"  [QueryAnalyzer] Intent: BOTH (doc={doc_score}, web={web_score})")
            return {
                "intent": SearchIntent.BOTH,
                "use_docs": True,
                "use_web": True
            }
        
        # Default: search docs first, fallback to web if no good results
        print(f"  [QueryAnalyzer] Intent: DOCUMENTS_ONLY (default, with web fallback)")
        return {
            "intent": SearchIntent.DOCUMENTS_ONLY,
            "use_docs": True,
            "use_web": False,
            "fallback_to_web": True
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

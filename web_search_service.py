"""
Web Search Service using DuckDuckGo Search
===========================================
Provides web search functionality for the RAG system.
"""

from typing import List, Dict


class WebSearchService:
    """
    Web search service that uses DuckDuckGo Search library.
    """
    
    def __init__(self):
        pass
    
    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """
        Search the web using DuckDuckGo.
        
        Args:
            query: Search query string
            num_results: Maximum number of results to return
            
        Returns:
            List of search results with title, snippet, url, and source
        """
        results = []
        
        try:
            from ddgs import DDGS
            
            # Enhance query for better results
            enhanced_query = query
            if not any(word in query.lower() for word in ['what is', 'define', 'meaning', 'explain']):
                # Add "what is" for definition-style queries
                if len(query.split()) <= 5:
                    enhanced_query = f"what is {query}"
            
            # Create fresh instance for each search
            with DDGS() as ddgs:
                search_results = list(ddgs.text(enhanced_query, max_results=num_results))
                
                for item in search_results:
                    # Filter out low-quality results
                    snippet = item.get("body", "")
                    if len(snippet) > 50:  # Only include results with substantial content
                        results.append({
                            "title": item.get("title", ""),
                            "snippet": snippet,
                            "url": item.get("href", ""),
                            "source": "web"
                        })
            
            print(f"  [WebSearch] Found {len(results)} results for: {query[:50]}...")
                
        except Exception as e:
            print(f"  [WebSearch] Error: {e}")
            # Fallback: return empty but don't crash
        
        return results[:num_results]
    
    def search_async(self, query: str, num_results: int = 5) -> List[Dict]:
        """Alias for search - can be made truly async if needed."""
        return self.search(query, num_results)

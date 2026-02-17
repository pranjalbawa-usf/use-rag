"""
Web Search Service using DuckDuckGo API
========================================
Provides web search functionality for the RAG system.
"""

import httpx
from typing import List, Dict, Optional


class WebSearchService:
    """
    Web search service that uses DuckDuckGo Instant Answer API.
    """
    
    def __init__(self):
        self.timeout = 10.0
    
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
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1
                    }
                )
                
                if response.status_code != 200:
                    print(f"  [WebSearch] API error: {response.status_code}")
                    return results
                
                data = response.json()
                
                # Get abstract if available (main answer)
                if data.get("Abstract"):
                    results.append({
                        "title": data.get("Heading", ""),
                        "snippet": data.get("Abstract", ""),
                        "url": data.get("AbstractURL", ""),
                        "source": "web"
                    })
                
                # Get related topics
                for topic in data.get("RelatedTopics", []):
                    if len(results) >= num_results:
                        break
                        
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:80],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", ""),
                            "source": "web"
                        })
                    elif isinstance(topic, dict) and topic.get("Topics"):
                        # Handle nested topics
                        for subtopic in topic.get("Topics", []):
                            if len(results) >= num_results:
                                break
                            if isinstance(subtopic, dict) and subtopic.get("Text"):
                                results.append({
                                    "title": subtopic.get("Text", "")[:80],
                                    "snippet": subtopic.get("Text", ""),
                                    "url": subtopic.get("FirstURL", ""),
                                    "source": "web"
                                })
                
                # Get definition if available
                if data.get("Definition") and len(results) < num_results:
                    results.append({
                        "title": f"Definition: {query}",
                        "snippet": data.get("Definition", ""),
                        "url": data.get("DefinitionURL", ""),
                        "source": "web"
                    })
                
                print(f"  [WebSearch] Found {len(results)} results for: {query[:50]}...")
                
        except httpx.TimeoutException:
            print(f"  [WebSearch] Timeout searching for: {query[:50]}...")
        except Exception as e:
            print(f"  [WebSearch] Error: {e}")
        
        return results[:num_results]
    
    def search_async(self, query: str, num_results: int = 5) -> List[Dict]:
        """Alias for search - can be made truly async if needed."""
        return self.search(query, num_results)

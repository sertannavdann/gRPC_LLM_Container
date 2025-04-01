import grpc
import requests
import random
from bs4 import BeautifulSoup
from concurrent import futures
from urllib.parse import urlparse
from typing import Dict, List
import tool_pb2
import tool_pb2_grpc
from grpc_reflection.v1alpha import reflection
from cachetools import cached, TTLCache
from selenium.webdriver import ChromeOptions
from seleniumwire import webdriver
from google.protobuf.struct_pb2 import Struct

# Configuration - Replace with your API credentials
SEARCH_API_KEY = "AIzaSyCkdzWNEowTmSbBxRMxV0R4w9X8nClN6ZM"
SEARCH_ENGINE_ID = "41b7b35fba4b24f40"
SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"

# Trusted domains and TLDs
CREDIBLE_DOMAINS = {".gov", ".edu", ".ac.", "wikipedia.org", "who.int"}
TRUSTED_TLDS = {".org", ".gov", ".edu"}

# Rotating user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

# Configure caching
cache = TTLCache(maxsize=1000, ttl=3600)

class ToolServiceServicer(tool_pb2_grpc.ToolServiceServicer):
    def __init__(self):
        self.proxies = self._load_proxies()  # Implement proxy loading logic
        
    def _load_proxies(self) -> List[str]:
        # Add your proxy rotation logic here
        return []

    @cached(cache)
    def _safe_fetch(self, url: str) -> str:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies={'http': random.choice(self.proxies)} if self.proxies else None,
                timeout=10
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            raise ValueError(f"HTTP error: {str(e)}")

    def _scrape_with_selenium(self, url: str) -> str:
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
        
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            return driver.page_source
        finally:
            driver.quit()

    def _sanitize_content(self, html: str) -> str:
        soup = BeautifulSoup(html, 'lxml')
        for element in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
            element.decompose()
        return soup.get_text(separator='\n', strip=True)[:15000]

    def _is_credible_source(self, url: str) -> bool:
        parsed = urlparse(url)
        return any(tld in parsed.netloc for tld in TRUSTED_TLDS) or \
               any(domain in parsed.netloc for domain in CREDIBLE_DOMAINS)

    def _search_engine_query(self, query: str, max_results: int = 5) -> List[Dict]:
        params = {
            "key": SEARCH_API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "q": query,
            "num": max_results,
            "safe": "active"
        }
        
        try:
            resp = requests.get(SEARCH_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get('items', [])
            return [{
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet")
            } for item in results]
        except Exception as e:
            raise ValueError(f"Search API error: {str(e)}")

    def CallTool(self, request, context):
        result = tool_pb2.ToolResponse()
        try:
            if request.tool_name == "web_scrape":
                return self._handle_basic_scrape(request, context)
            elif request.tool_name == "search_scrape":
                return self._handle_search_scrape(request, context)
            elif request.tool_name == "advanced_scrape":
                return self._handle_advanced_scrape(request, context)
            else:
                raise ValueError(f"Unknown tool: {request.tool_name}")
                
        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            result.output = f"Validation error: {str(e)}"
            result.success = False
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            result.output = f"Processing error: {str(e)}"
            result.success = False
            
        return result

    def _handle_basic_scrape(self, request, context) -> tool_pb2.ToolResponse:
        result = tool_pb2.ToolResponse()
        url_field = request.params.fields.get("url")
        
        if not url_field or url_field.WhichOneof('kind') != 'string_value':
            raise ValueError("Missing or invalid URL parameter")
        
        url = url_field.string_value
        if not urlparse(url).scheme:
            raise ValueError("Invalid URL scheme")
        
        content = self._safe_fetch(url)
        result.output = self._sanitize_content(content)
        result.success = True
        return result

    def _handle_search_scrape(self, request, context) -> tool_pb2.ToolResponse:
        result = tool_pb2.ToolResponse()
        params = request.params.fields
        
        query_field = params.get("query")
        if not query_field or query_field.WhichOneof('kind') != 'string_value':
            raise ValueError("Missing search query")
            
        max_results = int(params.get("max_results", 3).number_value or 3)
        credibility_threshold = float(params.get("credibility", 0.7).number_value or 0.7)
        
        # Execute search engine query
        search_results = self._search_engine_query(query_field.string_value, max_results)
        
        # Filter and process results
        combined_content = []
        structured_data = []
        
        for item in search_results:
            if not self._is_credible_source(item["link"]):
                continue
                
            try:
                content = self._safe_fetch(item["link"])
                sanitized = self._sanitize_content(content)
                
                combined_content.append(f"Source: {item['title']}\n\n{sanitized}")
                structured_data.append({
                    "title": item["title"],
                    "url": item["link"],
                    "snippet": item["snippet"],
                    "content_length": len(sanitized)
                })
            except Exception as e:
                continue

        if combined_content:
            result.output = "\n\n---\n\n".join(combined_content)
            result.success = True
            
            # Add structured data to response
            result.data.CopyFrom(Struct())
            result.data.update({"sources": structured_data})
        else:
            result.output = "No credible sources found"
            result.success = False
            
        return result

    def _handle_advanced_scrape(self, request, context) -> tool_pb2.ToolResponse:
        result = tool_pb2.ToolResponse()
        params = request.params.fields
        
        url_field = params.get("url")
        if not url_field or url_field.WhichOneof('kind') != 'string_value':
            raise ValueError("Missing URL parameter")
            
        use_js = params.get("use_js", False).bool_value or False
        extract_metadata = params.get("metadata", True).bool_value or True
        
        try:
            html = self._scrape_with_selenium(url_field.string_value) if use_js \
                else self._safe_fetch(url_field.string_value)
                
            soup = BeautifulSoup(html, 'lxml')
            result.output = self._sanitize_content(html)
            
            if extract_metadata:
                metadata = Struct()
                metadata.update({
                    "title": soup.title.string if soup.title else "",
                    "description": soup.find("meta", {"name": "description"})["content"] 
                                if soup.find("meta", {"name": "description"}) else "",
                    "keywords": soup.find("meta", {"name": "keywords"})["content"].split(",") 
                                if soup.find("meta", {"name": "keywords"}) else [],
                    "links": [a["href"] for a in soup.find_all("a", href=True)]
                })
                result.data.CopyFrom(metadata)
                
            result.success = True
        except Exception as e:
            raise RuntimeError(f"Advanced scrape failed: {str(e)}")
            
        return result

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    tool_pb2_grpc.add_ToolServiceServicer_to_server(ToolServiceServicer(), server)
    
    reflection.enable_server_reflection([
        tool_pb2.DESCRIPTOR.services_by_name['ToolService'].full_name,
        reflection.SERVICE_NAME
    ], server)
    
    server.add_insecure_port("[::]:50053")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
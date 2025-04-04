# tool_service.py
import grpc
import os
import requests
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from seleniumwire import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from cachetools import cached, TTLCache
from concurrent import futures
import tool_pb2
import tool_pb2_grpc
from grpc_reflection.v1alpha import reflection
from typing import Dict, Any

class ToolServiceServicer(tool_pb2_grpc.ToolServiceServicer):
    def __init__(self):
        # Configuration from environment
        self.search_api_key = os.getenv("SEARCH_API_KEY", "")
        self.search_engine_id = os.getenv("SEARCH_ENGINE_ID", "")
        
        # Reusable browser configuration
        self.chrome_options = ChromeOptions()
        self._configure_browser()
        
        # Trust lists from notebook
        self.credible_domains = {".gov", ".edu", ".ac.", "wikipedia.org", "who.int"}
        self.trusted_tlds = {".org", ".gov", ".edu"}
        
        # User agents from notebook
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]

    def _configure_browser(self):
        """Direct port of notebook's browser setup"""
        self.chrome_options.add_argument("--headless=new")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--remote-debugging-port=9222")
        self.chrome_options.add_argument("--disable-gpu")
        if os.path.exists('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
            self.chrome_options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

    def _selenium_scrape(self, url: str) -> str:
        """Direct port of notebook's test_selenium_scrape"""
        try:
            self.chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")
            service = Service(ChromeDriverManager().install())
            
            with webdriver.Chrome(service=service, options=self.chrome_options) as driver:
                driver.get(url)
                return driver.page_source
        except Exception as e:
            raise RuntimeError(f"Selenium failed: {str(e)}")

    def _sanitize_content(self, html: str) -> str:
        """Direct port of notebook's sanitization logic"""
        try:
            soup = BeautifulSoup(html, 'lxml')
        except Exception:
            soup = BeautifulSoup(html, 'html.parser')
            
        for element in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
            element.decompose()
            
        return soup.get_text(separator='\n', strip=True)[:15000]

    def CallTool(self, request, context):
        response = tool_pb2.ToolResponse()
        try:
            params = {k: v.string_value for k, v in request.params.fields.items()}
            
            if request.tool_name == "web_scrape":
                if not (url := params.get("url")):
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    response.output = "Missing URL parameter"
                    return response
                
                if not urlparse(url).scheme:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    response.output = "Invalid URL format"
                    return response

                # Direct port of notebook's test_basic_scrape logic
                try:
                    headers = {"User-Agent": random.choice(self.user_agents)}
                    resp = requests.get(url, headers=headers, timeout=10)
                    html = resp.text
                except requests.RequestException:
                    html = self._selenium_scrape(url)
                
                response.output = self._sanitize_content(html)
                response.success = True

            elif request.tool_name == "web_search":
                if not self.search_api_key:
                    context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                    response.output = "Search API not configured"
                    return response
                
                # Direct port of notebook's test_search logic
                params = {
                    "key": self.search_api_key,
                    "cx": self.search_engine_id,
                    "q": params.get("query", ""),
                    "num": min(int(params.get("max_results", 3)), 10),
                    "safe": "active"
                }
                
                results = requests.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=15
                ).json()
                
                response.output = "\n".join(
                    f"{item['title']}\n{item['link']}\n{item['snippet']}" 
                    for item in results.get('items', [])
                )
                response.success = True

            elif request.tool_name == "credibility_check":
                # Direct port of notebook's test_credible_source
                parsed = urlparse(params.get("url", ""))
                response.output = str(
                    any(tld in parsed.netloc for tld in self.trusted_tlds) or
                    any(domain in parsed.netloc for domain in self.credible_domains)
                )
                response.success = True

            else:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                response.output = f"Unknown tool: {request.tool_name}"

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            response.output = f"Tool error: {str(e)}"
            response.success = False
            
        return response

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
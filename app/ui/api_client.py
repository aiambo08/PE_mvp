import requests
from typing import Dict, Any, Optional

class APIClient:
    def __init__(self, base_url: str= "http://localhost:8000/api/v1"):
        self.base_url = base_url
    
    def check_health(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=3)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False
    
    def analyze_company(self, url: str) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/analyze_company"
        response = requests.post(endpoint, json={"url":url}, timeout=120)
        response.raise_for_status()
        return response.json()
    
    def upload_document(self, company_domain: str, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/upload_document"
        files = {"file": (filename, file_bytes, "application/pdf")}
        data = {"company_domain": company_domain}
        response = requests.post(endpoint, data=data, files=files, timeout=60)
        response.raise_for_status()
        return response.json()
    
    def query_rag(self, query: str, company_domain: Optional[str] = None, top_k: int=4) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/query-rag"
        payload = {"query": query, "company_domain": company_domain, "top_k":top_k}
        response = requests.post(endpoint, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    
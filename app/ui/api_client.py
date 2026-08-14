import os
import requests
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self):
        # Lee de variables de entorno, con fallback a localhost para dev sin Docker
        self.base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Encapsula el manejo de errores para que la UI no reciba trazas crudas."""
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = response.json().get("detail", str(e)) if response.text else str(e)
            raise ValueError(f"Error del servidor: {error_detail}")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Fallo de conexión con el backend: {str(e)}")

    def check_health(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=3)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def analyze_company(self, url: str) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/analyze-company"
        response = requests.post(endpoint, json={"url": url}, timeout=120)
        return self._handle_response(response)
    
    def upload_document(self, company_domain: str, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/upload-document"
        files = {"file": (filename, file_bytes, "application/pdf")}
        data = {"company_domain": company_domain}
        response = requests.post(endpoint, data=data, files=files, timeout=60)
        return self._handle_response(response)
    
    def query_rag(self, query: str, company_domain: Optional[str] = None, top_k: int = 4) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/query-rag"
        payload = {"query": query, "company_domain": company_domain, "top_k": top_k}
        response = requests.post(endpoint, json=payload, timeout=60)
        return self._handle_response(response)

    def list_companies(self) -> List[Dict[str, Any]]:
        endpoint = f"{self.base_url}/companies"
        response = requests.get(endpoint, timeout=15)
        return self._handle_response(response)

    def simulate_leverage(
        self,
        revenue: float,
        ebitda: float,
        net_debt: float,
        max_covenant_ratio: float = 3.0,
        fixed_cost_ratio: float = 0.60,
        annual_debt_service: Optional[float] = None,
    ) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/simulate-leverage"
        payload = {
            "revenue": revenue,
            "ebitda": ebitda,
            "net_debt": net_debt,
            "max_covenant_ratio": max_covenant_ratio,
            "fixed_cost_ratio": fixed_cost_ratio,
            "annual_debt_service": annual_debt_service,
        }
        response = requests.post(endpoint, json=payload, timeout=15)
        return self._handle_response(response)

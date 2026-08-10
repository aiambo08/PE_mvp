import asyncio
from pathlib import Path
import httpx

API_BASE_URL = "http://localhost:8000/api/v1"

# Ruta robusta apuntando a la carpeta docs en la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
PDF_FILE_PATH = BASE_DIR.parent / "docs" / "cim_sample_logistics_veloz.pdf"
COMPANY_DOMAIN = "logistics-veloz.com"


async def test_rag_pipeline():
    if not PDF_FILE_PATH.exists():
        print(f"❌ Archivo no encontrado en: {PDF_FILE_PATH}")
        return

    async with httpx.AsyncClient(timeout=60.0) as client:
        print("=== 1. SUBIENDO E INDEXANDO PDF EN QDRANT ===")
        with open(PDF_FILE_PATH, "rb") as pdf_file:
            response = await client.post(
                f"{API_BASE_URL}/upload-document",
                data={"company_domain": COMPANY_DOMAIN},
                files={"file": (PDF_FILE_PATH.name, pdf_file, "application/pdf")}
            )

        if response.status_code != 200:
            print(f"❌ Error al subir documento: {response.text}")
            return

        upload_data = response.json()
        print("✅ Documento indexado correctamente:")
        print(f"   • ID Documento: {upload_data['document_id']}")
        print(f"   • Chunks Creados: {upload_data['chunks_indexed']}")
        print(f"   • Páginas: {upload_data['total_pages']}\n")

        print("=== 2. REALIZANDO CONSULTAS DE DUE DILIGENCE CON RAG ===")

        test_queries = [
            "¿Cuál es el EBITDA normalizado de la compañía en el año FY2025 y qué margen representa sobre las ventas?",
            "¿Cuáles son los covenants bancarios exigidos por el banco y cuál es el ratio DFN/EBITDA actual?",
            "¿Existe alguna cláusula de Change of Control en los contratos principales con clientes y qué exige?"
        ]

        for idx, query in enumerate(test_queries, 1):
            print(f"❓ PREGUNTA {idx}: {query}")

            payload = {
                "query": query,
                "company_domain": COMPANY_DOMAIN,
                "top_k": 3
            }

            query_response = await client.post(f"{API_BASE_URL}/query-rag", json=payload)

            if query_response.status_code == 200:
                result = query_response.json()
                print(f"🤖 RESPUESTA LLM ({result['retrieval_time_ms']} ms):")
                print(f"{result['answer']}\n")

                print("📌 CITAS DE FUENTE RECUPERADAS:")
                for citation in result["citations"]:
                    print(
                        f"   • Página {citation['page_number']} (Score: {citation['score']}): "
                        f"\"{citation['excerpt'][:120]}...\""
                    )
                print("-" * 80 + "\n")
            else:
                print(f"❌ Error en consulta RAG: {query_response.text}\n")


if __name__ == "__main__":
    asyncio.run(test_rag_pipeline())
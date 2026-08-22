"""
Extracts main page, key internal pages, contact emails, and social links
from a target company domain.

ARQUITECTURA (Windows-safe):
    Playwright necesita ProactorEventLoop en Windows para lanzar Chromium
    como subproceso. Uvicorn (SelectorEventLoop) no lo proporciona.
    Solución: usar playwright.sync_api dentro de un ThreadPoolExecutor.
    Cada scraping corre en su propio hilo con su propio contexto Playwright,
    completamente aislado del event loop de Uvicorn.
"""

from __future__ import annotations

import asyncio
import logging
import re
import concurrent.futures
from datetime import datetime, UTC
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import (
    sync_playwright,
    BrowserContext as SyncBrowserContext,
    Page as SyncPage,
)

from app.models.raw_schemas import PageContent, RawCompanyData

logger = logging.getLogger(__name__)

_SOCIAL_DOMAINS = ("linkedin.com", "twitter.com", "x.com", "instagram.com", "facebook.com")
_TARGET_KEYWORDS = ("sobre", "about", "nosotros", "servicios", "services", "contacto", "contact")
_MAX_SUBPAGES = 3

# Pool de hilos limitado: evita abrir demasiados browsers en paralelo
_SCRAPER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=3, thread_name_prefix="playwright-worker"
)


class CompanyWebScraper:
    """
    Scraper que extrae datos estructurados de una empresa usando Playwright (Chromium).

    Usa la API SÍNCRONA de Playwright en un ThreadPoolExecutor para ser
    compatible con cualquier event loop (SelectorEventLoop o ProactorEventLoop).
    La interfaz pública es async para integrarse limpiamente con FastAPI/asyncio.
    """

    def __init__(self, headless: bool = True, timeout: int = 30_000) -> None:
        self.headless = headless
        self.timeout = timeout
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )

    # ── Utilidades puras (sin I/O) ────────────────────────────────────────────

    def _clean_html_to_text(self, html_content: str) -> str:
        """Elimina elementos HTML no relevantes y retorna texto limpio."""
        soup = BeautifulSoup(html_content, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "iframe", "noscript", "svg"]):
            element.decompose()
        text = soup.get_text(separator=" ")
        return re.sub(r"\s+", " ", text).strip()

    def _extract_emails(self, text: str) -> Optional[str]:
        """Retorna la primera dirección de email encontrada en el texto, o None."""
        matches = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        return matches[0] if matches else None

    def _extract_social_links(self, links: list[str]) -> list[str]:
        """Retorna URLs de redes sociales sin duplicados."""
        return list({
            link for link in links
            if any(domain in link for domain in _SOCIAL_DOMAINS)
        })

    def _normalize_url(self, raw: str) -> tuple[str, str]:
        """Normaliza un dominio o URL en (base_url, domain)."""
        raw = raw.strip().lower()
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        domain = parsed.netloc or parsed.path
        if ":" in domain:
            domain = domain.split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        domain = domain.strip("/")
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return base_url, domain

    # ── Lógica síncrona de Playwright (se ejecuta en hilo separado) ───────────

    def _scrape_single_page_sync(
        self, context: SyncBrowserContext, url: str
    ) -> Optional[PageContent]:
        """Abre una página nueva en el contexto dado y extrae su contenido."""
        page: Optional[SyncPage] = None
        try:
            page = context.new_page()
            response = page.goto(url, wait_until="networkidle", timeout=self.timeout)
            if not response or response.status >= 400:
                logger.warning("HTTP %s for URL: %s", response and response.status, url)
                return None
            page.wait_for_timeout(2_000)  # Allow SPA frameworks (React/Next.js) to fully hydrate
            html = page.content()
            title = page.title()
            cleaned_text = self._clean_html_to_text(html)
            return PageContent(
                url=url,
                title=title,
                raw_text=cleaned_text,
                word_count=0,  # Calculado por @model_validator en PageContent
                extracted_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("Scraping failed for URL: %s", url)
            return None
        finally:
            if page:
                page.close()

    def _scrape_company_sync(self, domain_or_url: str) -> RawCompanyData:
        """
        Lógica principal de scraping. Corre en un hilo dedicado con sync_playwright.

        CRÍTICO EN WINDOWS: sync_playwright() crea su propio asyncio event loop
        internamente usando la policy de proceso. Uvicorn fuerza SelectorEventLoop,
        que no soporta subprocesos. Fijamos ProactorEventLoop al inicio del hilo
        antes de que Playwright cree su loop interno.
        """
        import sys
        import asyncio
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        base_url, domain = self._normalize_url(domain_or_url)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            try:
                context = browser.new_context(
                    user_agent=self._user_agent,
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    # ── 1. Página principal ───────────────────────────────
                    main_page_data = self._scrape_single_page_sync(context, base_url)
                    if not main_page_data:
                        return RawCompanyData(
                            company_domain=domain,
                            base_url=base_url,
                            main_page=PageContent(
                                url=base_url, title="", raw_text="", word_count=0
                            ),
                            scrape_status="FAILED",
                            error_message="Could not access the main page.",
                        )

                    # ── 2. Descubrir enlaces internos ─────────────────────
                    nav_page = context.new_page()
                    try:
                        nav_page.goto(base_url, wait_until="networkidle", timeout=self.timeout)
                        all_links: list[str] = nav_page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)"
                        )
                    finally:
                        nav_page.close()

                    relevant_urls = sorted([
                        link
                        for link in dict.fromkeys(all_links)  # deduplica
                        if domain in link
                        and any(kw in link.lower() for kw in _TARGET_KEYWORDS)
                        and link.rstrip("/") != base_url.rstrip("/")
                    ])[:_MAX_SUBPAGES]  # sorted() ensures deterministic subpage selection

                    social_links = self._extract_social_links(all_links)

                    # ── 3. Scraping de subpáginas (secuencial en el hilo) ─
                    subpages_data: list[PageContent] = []
                    for url in relevant_urls:
                        result = self._scrape_single_page_sync(context, url)
                        if result:
                            subpages_data.append(result)

                    # ── 4. Extracción de email ────────────────────────────
                    full_text = " ".join(
                        [main_page_data.raw_text] + [sp.raw_text for sp in subpages_data]
                    )
                    contact_email = self._extract_emails(full_text)
                    scrape_status = "SUCCESS" if subpages_data or not relevant_urls else "PARTIAL"

                    return RawCompanyData(
                        company_domain=domain,
                        base_url=base_url,
                        main_page=main_page_data,
                        internal_pages=subpages_data,
                        contact_email=contact_email,
                        social_links=social_links,
                        scrape_status=scrape_status,
                    )
                finally:
                    context.close()
            finally:
                browser.close()

    # ── Interfaz pública async (compatible con FastAPI) ───────────────────────

    async def scrape_company(self, domain_or_url: str) -> RawCompanyData:
        """
        Punto de entrada async. Delega el scraping al ThreadPoolExecutor global
        para no bloquear el event loop de Uvicorn ni depender de su tipo.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _SCRAPER_EXECUTOR,
            self._scrape_company_sync,
            domain_or_url,
        )


# ── Punto de entrada para prueba directa ─────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = CompanyWebScraper(headless=True)
    result = scraper._scrape_company_sync("scale.com")
    logger.info("Status       : %s", result.scrape_status)
    logger.info("Home words   : %d", result.main_page.word_count)
    logger.info("Subpages     : %d", len(result.internal_pages))
    logger.info("Email found  : %s", result.contact_email)
    logger.info("Social links : %s", result.social_links)
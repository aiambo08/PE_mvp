"""
Extracts main page, key internal pages, contact emails, and social links from a target company domain.
"""


from __future__ import annotations
import asyncio
import logging
import re
from datetime import datetime, UTC
from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)
from app.models.raw_schemas import PageContent, RawCompanyData

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)
_SOCIAL_DOMAINS = ("linkedin.com", "twitter.com", "x.com", "instagram.com", "facebook.com")
_TARGET_KEYWORDS = ("sobre", "about", "nosotros", "servicios", "services", "contacto", "contact")
_MAX_SUBPAGES = 3

class CompanyWebScraper:
    """
    Async scraper that extracts structured raw data from a company website.
    Uses Playwright (Chromium) to handle JavaScript-heavy pages.
    Each call to `scrape_company` is fully isolated in its own browser context.
    """
    def __init__(self, headless: bool = True, timeout: int = 30000) -> None:
        self.headless = headless
        self.timeout = timeout
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )

    def _clean_html_to_text(self, html_content:str) -> str:
        """Strip non-content HTML elements and return clean plain text."""
        soup = BeautifulSoup(html_content, 'html.parser')
        # Eliminar elementos no importantes
        for element in soup(["script", "style", "nav", "footer", "iframe", "noscript", "svg"]):
            element.decompose()
        
        # Obtener texto plano y limpiar
        text = soup.get_text(separator=" ")
        # Eliminar espacios en blanco excesivos, saltos de línea y tabulaciones
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _extract_emails(self, text:str) -> Optional[str]:
        """Return the first email address found in text, or None."""
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        matches = re.findall(email_pattern, text)
        return matches if matches else None

    def _extract_social_links(self, links: list[str]) -> list[str]:
        """Return deduplicated social media URLs found in a list of links."""
        return list({
            link for link in links
            if any(domain in link for domain in _SOCIAL_DOMAINS)
        })
    def _normalize_url(self, raw: str) -> tuple[str, str]:
        """
        Normalize a raw domain or URL into (base_url, domain).
        Returns:
            Tuple of (full base URL, netloc/domain string).
        """
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return base_url, parsed.netloc

    async def _scrape_single_page(
        self, context: BrowserContext, url: str
    ) -> Optional[PageContent]:
        """
        Open a fresh page in the given browser context and scrape `url`.
        Returns:
            A `PageContent` instance, or None if the page is unreachable.
        """
        page: Optional[Page] = None
        try:
            page = await context.new_page()
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout
            )
            if not response or response.status >= 400:
                logger.warning("HTTP %s for URL: %s", response and response.status, url)
                return None
            await page.wait_for_timeout(1_000)
            html = await page.content()
            title = await page.title()
            cleaned_text = self._clean_html_to_text(html)
            return PageContent(
                url=url,
                title=title,
                raw_text=cleaned_text,
                word_count=0,  # Overridden by @model_validator
                extracted_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("Scraping failed for URL: %s", url)
            return None
        finally:
            if page:
                await page.close()

    async def scrape_company(self, domain_or_url: str) -> RawCompanyData:
        """
        Scrape a company's website and return a `RawCompanyData` aggregate.
        Args:
            domain_or_url: A bare domain (e.g. "acme.com") or full URL.
        Returns:
            A validated `RawCompanyData` instance with status SUCCESS,
            PARTIAL, or FAILED.
        """
        base_url, domain = self._normalize_url(domain_or_url)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.headless)
            try:
                context = await browser.new_context(
                    user_agent=self._user_agent,
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    # ── 1. Main page ──────────────────────────────────────
                    main_page_data = await self._scrape_single_page(context, base_url)
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
                    # ── 2. Discover internal links ────────────────────────
                    # Reuse a lightweight page just for link extraction
                    nav_page = await context.new_page()
                    try:
                        await nav_page.goto(
                            base_url, wait_until="domcontentloaded", timeout=self.timeout
                        )
                        all_links: list[str] = await nav_page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)"
                        )
                    finally:
                        await nav_page.close()
                    relevant_urls = [
                        link
                        for link in dict.fromkeys(all_links)  # deduplicate, preserve order
                        if domain in link
                        and any(kw in link.lower() for kw in _TARGET_KEYWORDS)
                        and link.rstrip("/") != base_url.rstrip("/")
                    ][:_MAX_SUBPAGES]
                    social_links = self._extract_social_links(all_links)
                    # ── 3. Parallel subpage scraping ──────────────────────
                    tasks = [
                        self._scrape_single_page(context, url)
                        for url in relevant_urls
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    subpages_data = [
                        r for r in results
                        if isinstance(r, PageContent)
                    ]
                    # ── 4. Email extraction ───────────────────────────────
                    full_text = " ".join(
                        [main_page_data.raw_text] + [sp.raw_text for sp in subpages_data]
                    )
                    contact_email = self._extract_emails(full_text)
                    scrape_status: str = (
                        "SUCCESS" if subpages_data or not relevant_urls else "PARTIAL"
                    )
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
                    await context.close()
            finally:
                await browser.close()

# Punto de entrada para prueba directa
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    async def _test() -> None:
        scraper = CompanyWebScraper(headless=True)
        result = await scraper.scrape_company("scale.com")
        logger.info("Status       : %s", result.scrape_status)
        logger.info("Home words   : %d", result.main_page.word_count)
        logger.info("Subpages     : %d", len(result.internal_pages))
        logger.info("Email found  : %s", result.contact_email)
        logger.info("Social links : %s", result.social_links)
    asyncio.run(_test())
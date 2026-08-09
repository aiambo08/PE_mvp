from __future__ import annotations
import logging
from datetime import datetime, UTC
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
logger = logging.getLogger(__name__)

class PageContent(BaseModel):
    """Represents the scraped content of a single web page."""
    url: str
    title: str
    raw_text: str
    word_count: int = Field(default=0, ge=0)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    @model_validator(mode="after")
    def sync_word_count(self) -> "PageContent":
        """Ensure word_count always reflects the actual raw_text length."""
        self.word_count = len(self.raw_text.split())
        return self


class RawCompanyData(BaseModel):
    """Aggregated raw data extracted from a company's web presence."""
    company_domain: str
    base_url: str
    main_page: PageContent
    internal_pages: List[PageContent] = Field(default_factory=list)
    contact_email: Optional[str] = None
    social_links: List[str] = Field(default_factory=list)
    scrape_status: Literal["SUCCESS", "PARTIAL", "FAILED"] = "SUCCESS"
    error_message: Optional[str] = None
    

    
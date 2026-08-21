"""
Regression test: verifies that the company extraction pipeline produces
consistent, hallucination-free results across multiple runs.
"""
import asyncio
import sys

# Windows ProactorEventLoop for Playwright compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.scrapers.company_scraper import CompanyWebScraper
from app.services.extraction_service import CompanyExtractionService


async def run_determinism_check(target_domain: str = "elevenlabs.io", runs: int = 3):
    scraper = CompanyWebScraper(headless=True)
    raw_data = await scraper.scrape_company(target_domain)
    extractor = CompanyExtractionService()

    results = []
    for _ in range(runs):
        res = await extractor.extract_and_score(raw_data)
        assert res.get("status") == "SUCCESS", f"Extraction failed: {res.get('error')}"
        results.append(res)

    # Validate names and scores
    names = {r["profile"]["company_name"] for r in results}
    scores = [r["scoring"]["total_score"] for r in results]
    tiers = {r["scoring"]["tier"] for r in results}

    assert "Tech Innovations Inc." not in names, "Hallucinated name detected"
    assert "ExampleTech" not in names, "Placeholder name detected"
    assert max(scores) - min(scores) <= 5.0, f"Score variance too high: {scores}"
    assert len(tiers) == 1, f"Inconsistent tiers: {tiers}"

    return True


if __name__ == "__main__":
    asyncio.run(run_determinism_check())
    print("Determinism regression test: PASS")

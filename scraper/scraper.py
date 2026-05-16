import logging
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from .robots import check_robots_txt, get_crawl_delay

logger = logging.getLogger("smart_api_tool")
USER_AGENT = "SmartAPITool/1.0"


def extract_main_content(soup):
    from markdownify import markdownify as md

    # Try to find the main content area using common selectors
    for selector in [
        "main",
        "article",
        "section",
        "div.content",
        "div.docs",
        "[role='main']",
    ]:
        element = soup.select_one(selector)
        if element:
            return md(str(element), heading_style="ATX").strip()

    # If no main area found, clean up noise tags and get everything else
    for tag in soup(["nav", "footer", "header", "script", "style", "aside"]):
        tag.decompose()

    return md(str(soup), heading_style="ATX").strip()


def scrape_url(url):
    if not check_robots_txt(url):
        raise PermissionError(f"robots.txt disallows scraping: {url}")

    # Respect the site's crawl delay
    delay = get_crawl_delay(url)
    time.sleep(delay)

    logger.info(f"Scraping static page: {url}")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    return extract_main_content(soup)


def scrape_with_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed, falling back to requests")
        return scrape_url(url)

    if not check_robots_txt(url):
        raise PermissionError(f"robots.txt disallows scraping: {url}")

    time.sleep(get_crawl_delay(url))

    logger.info(f"Scraping JS page with Playwright: {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    return extract_main_content(soup)


def scrape_with_pagination(base_url, max_pages=5):
    visited = set()
    texts = []
    to_visit = [base_url]
    base_domain = urlparse(base_url).netloc

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)

        if url in visited:
            continue

        visited.add(url)
        logger.info(f"Scraping page {len(visited)}/{max_pages}: {url}")

        try:
            # scrape_url automatically checks robots.txt and sleeps
            page_text = scrape_url(url)
            texts.append(page_text)

            # Fetch again quickly just to find the links for the next iteration
            res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")

            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                parsed_link = urlparse(link)

                # Check if it's the same domain and looks like an API link
                if parsed_link.netloc == base_domain:
                    is_api = any(
                        kw in parsed_link.path
                        for kw in ["/api", "/endpoint", "/reference", "/docs", "/guide"]
                    )
                    if is_api and link not in visited and link not in to_visit:
                        to_visit.append(link)

        except Exception as e:
            logger.warning(f"Error scraping {url}: {e}")

    return "\n\n---PAGE BREAK---\n\n".join(texts)


def is_graphql_endpoint(url: str) -> bool:
    """Heuristic check for common GraphQL endpoint URL patterns."""
    clean = url.rstrip("/")
    return (
        clean.endswith("/graphql")
        or "/graphql/" in clean
        or "/api/graphql" in clean
    )


def scrape(url, use_playwright=False, follow_links=False, max_pages=5):
    if is_graphql_endpoint(url):
        logger.warning(
            "Detected GraphQL-style endpoint %s. "
            "Consider using --graphql mode for introspection-based parsing.",
            url,
        )
    if follow_links:
        return scrape_with_pagination(url, max_pages)
    elif use_playwright:
        return scrape_with_playwright(url)
    else:
        return scrape_url(url)

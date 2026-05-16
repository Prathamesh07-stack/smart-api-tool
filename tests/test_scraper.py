from scraper.scraper import scrape_url


def test_scrape_returns_text():
    """Verify that the scraper successfully extracts text from a known URL."""
    url = "https://jsonplaceholder.typicode.com/"
    text = scrape_url(url)
    assert isinstance(text, str)
    assert len(text) > 200
    assert "posts" in text.lower() or "users" in text.lower()

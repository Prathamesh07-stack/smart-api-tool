import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("smart_api_tool")
USER_AGENT = "SmartAPITool/1.0"


def get_robots_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def check_robots_txt(url):
    try:
        robots_url = get_robots_url(url)
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()

        if not rp.can_fetch(USER_AGENT, url):
            logger.warning(f"robots.txt disallows scraping: {url}")
            return False

        return True
    except Exception as e:
        logger.warning(f"Could not read robots.txt for {url}, assuming allowed: {e}")
        return True


def get_crawl_delay(url):
    try:
        robots_url = get_robots_url(url)
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()

        delay = rp.crawl_delay(USER_AGENT)
        if delay:
            return float(delay)
        return 1.0
    except Exception:
        return 1.0

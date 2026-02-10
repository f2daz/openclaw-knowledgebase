"""Web crawler for OpenClaw Knowledgebase."""

import hashlib
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterator
from urllib.parse import urljoin, urlparse

import requests

from knowledgebase.config import get_config

logger = logging.getLogger(__name__)

# Optional imports
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import html2text
    HAS_HTML2TEXT = True
except ImportError:
    HAS_HTML2TEXT = False


@dataclass
class CrawledPage:
    """A crawled web page."""
    url: str
    title: str | None
    content: str  # Markdown content
    html: str | None = None
    content_hash: str = ""
    links: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.content_hash and self.content:
            self.content_hash = hashlib.md5(self.content.encode()).hexdigest()


def check_crawler_deps() -> tuple[bool, str]:
    """Check if crawler dependencies are installed."""
    missing = []
    if not HAS_BS4:
        missing.append("beautifulsoup4")
    if not HAS_HTML2TEXT:
        missing.append("html2text")
    
    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}. Install with: pip install {' '.join(missing)}"
    return True, "OK"


def html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown."""
    if not HAS_HTML2TEXT:
        # Fallback: strip tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()
    
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # No wrapping
    h.unicode_snob = True
    h.skip_internal_links = True
    h.inline_links = True
    h.protect_links = True
    
    return h.handle(html).strip()


def extract_links(soup: "BeautifulSoup", base_url: str) -> list[str]:
    """Extract all links from a page."""
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Skip anchors, javascript, mailto
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        # Make absolute
        absolute = urljoin(base_url, href)
        # Only keep http(s) links
        if absolute.startswith(("http://", "https://")):
            # Remove fragment
            absolute = absolute.split("#")[0]
            links.append(absolute)
    return list(set(links))


def extract_title(soup: "BeautifulSoup") -> str | None:
    """Extract page title."""
    # Try <title>
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    # Try <h1>
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def extract_main_content(soup: "BeautifulSoup") -> str:
    """Extract main content, removing nav/footer/etc."""
    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()
    
    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r"content|main|article", re.I))
    
    if main:
        return str(main)
    
    # Fallback to body
    body = soup.find("body")
    return str(body) if body else str(soup)


def crawl_url(
    url: str,
    timeout: int = 30,
    user_agent: str = "OpenClaw-Knowledgebase/1.0",
) -> CrawledPage | None:
    """
    Crawl a single URL.
    
    Args:
        url: URL to crawl
        timeout: Request timeout in seconds
        user_agent: User agent string
        
    Returns:
        CrawledPage or None on error
    """
    ok, msg = check_crawler_deps()
    if not ok:
        raise ImportError(msg)
    
    try:
        headers = {"User-Agent": user_agent}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return None
        
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        title = extract_title(soup)
        main_html = extract_main_content(soup)
        content = html_to_markdown(main_html)
        links = extract_links(soup, url)
        
        return CrawledPage(
            url=url,
            title=title,
            content=content,
            html=html,
            links=links,
            metadata={
                "content_type": content_type,
                "content_length": len(content),
            },
        )
        
    except Exception:
        logger.exception("crawl_url failed", extra={"url": url})
        return None


def normalize_domain(domain: str) -> str:
    """Normalize domain by removing www. prefix."""
    return domain.lower().removeprefix("www.")


def crawl_website(
    start_url: str,
    max_depth: int = 2,
    max_pages: int = 100,
    same_domain_only: bool = True,
    rate_limit: float = 1.0,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Iterator[CrawledPage]:
    """
    Crawl a website starting from a URL.
    
    Args:
        start_url: Starting URL
        max_depth: Maximum link depth to follow (0 = only start_url)
        max_pages: Maximum pages to crawl
        same_domain_only: Only follow links on same domain
        rate_limit: Seconds between requests
        progress_callback: Called with (crawled, total, current_url)
        
    Yields:
        CrawledPage objects
    """
    ok, msg = check_crawler_deps()
    if not ok:
        raise ImportError(msg)
    
    start_domain = normalize_domain(urlparse(start_url).netloc)
    
    # Queue: (url, depth)
    queue = deque([(start_url, 0)])
    visited = set()
    crawled = 0
    
    while queue and crawled < max_pages:
        url, depth = queue.popleft()
        
        # Skip if already visited
        if url in visited:
            continue
        visited.add(url)
        
        # Progress callback
        if progress_callback:
            progress_callback(crawled, len(queue) + crawled, url)
        
        # Crawl
        page = crawl_url(url)
        if page:
            yield page
            crawled += 1
            
            # Add links to queue if not at max depth
            if depth < max_depth:
                for link in page.links:
                    if link not in visited:
                        # Check domain (normalize to handle www vs non-www)
                        if same_domain_only:
                            link_domain = normalize_domain(urlparse(link).netloc)
                            if link_domain != start_domain:
                                continue
                        queue.append((link, depth + 1))
            
            # Rate limiting
            if rate_limit > 0 and queue:
                time.sleep(rate_limit)


def crawl_sitemap(
    sitemap_url: str,
    max_pages: int = 100,
    rate_limit: float = 1.0,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Iterator[CrawledPage]:
    """
    Crawl URLs from a sitemap.xml.
    
    Args:
        sitemap_url: URL to sitemap.xml
        max_pages: Maximum pages to crawl
        rate_limit: Seconds between requests
        progress_callback: Called with (crawled, total, current_url)
        
    Yields:
        CrawledPage objects
    """
    ok, msg = check_crawler_deps()
    if not ok:
        raise ImportError(msg)
    
    try:
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "xml")
        urls = [loc.text for loc in soup.find_all("loc")]
        
        total = min(len(urls), max_pages)
        
        for i, url in enumerate(urls[:max_pages]):
            if progress_callback:
                progress_callback(i, total, url)
            
            page = crawl_url(url)
            if page:
                yield page
            
            if rate_limit > 0 and i < total - 1:
                time.sleep(rate_limit)
                
    except Exception:
        logger.exception("crawl_sitemap failed", extra={"sitemap_url": sitemap_url})
        return

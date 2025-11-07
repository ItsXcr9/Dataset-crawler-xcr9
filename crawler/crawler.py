#!/usr/bin/env python3
"""
Professional Web Crawler for Dataset Creation
Recursively crawls websites and extracts content for LLM training datasets.
"""

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
import json
import hashlib
import time
from urllib.parse import urlparse, urljoin
import re
from datetime import datetime
import os
from typing import Set, Dict, List
import structlog
from prometheus_client import Counter, Gauge, Histogram

# Metrics
CRAWLED_PAGES = Counter('crawler_pages_total', 'Total pages crawled')
EXTRACTED_LINKS = Counter('crawler_links_total', 'Total links extracted')
PROCESSING_TIME = Histogram('crawler_processing_seconds', 'Time spent processing pages')

logger = structlog.get_logger()


class ProfessionalCrawler(CrawlSpider):
    name = 'professional_crawler'

    # Dynamic rules - will be set in __init__
    rules = ()

    def __init__(self, start_urls=None, allowed_domains=None, max_depth=3,
                 output_dir='dataset/raw', *args, **kwargs):
        # Set attributes BEFORE calling super().__init__()
        self.start_urls = start_urls or []
        self.allowed_domains = allowed_domains or []
        self.max_depth = int(max_depth)
        self.output_dir = output_dir
        self.visited_urls: Set[str] = set()
        self.crawled_data: List[Dict] = []

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize link extractor with custom settings
        self.link_extractor = LinkExtractor(
            allow_domains=self.allowed_domains,
            deny_extensions=['.pdf', '.doc', '.docx', '.xls', '.xlsx',
                           '.ppt', '.pptx', '.zip', '.rar', '.7z',
                           '.tar', '.gz', '.bz2', '.exe', '.dmg'],
            tags=['a', 'area'],
            attrs=['href'],
            canonicalize=True,
            unique=True
        )

        # Set up rules for crawling BEFORE calling super().__init__()
        self.rules = (
            Rule(
                self.link_extractor,
                callback='parse_item',
                follow=True,
                process_request='process_request'
            ),
        )
        
        # Now initialize the parent CrawlSpider
        super().__init__(*args, **kwargs)

        logger.info("Crawler initialized", start_urls=self.start_urls,
                   allowed_domains=self.allowed_domains, max_depth=self.max_depth)

    def parse_start_url(self, response):
        """Parse the start URL (required for CrawlSpider with rules)"""
        return self.parse_item(response)

    def process_request(self, request, response):
        """Process request before sending"""
        # Check depth
        depth = response.meta.get('depth', 0)
        if depth > self.max_depth:
            logger.debug("Skipping URL due to max depth", url=request.url, depth=depth)
            return None

        # Check if already visited
        if request.url in self.visited_urls:
            logger.debug("Skipping already visited URL", url=request.url)
            return None

        self.visited_urls.add(request.url)
        EXTRACTED_LINKS.inc()
        return request

    @PROCESSING_TIME.time()
    def parse_item(self, response):
        """Parse crawled page and extract content"""
        try:
            # Extract basic page information
            url = response.url
            title = self.extract_title(response)
            text_content = self.extract_text_content(response)
            links = self.extract_links(response)

            logger.info("Processing page", url=url, title=title[:50] if title else "No title", 
                       content_length=len(text_content) if text_content else 0,
                       links_found=len(links))

            if not text_content or len(text_content.strip()) < 100:
                logger.info("Skipping page with insufficient content", url=url, 
                           content_length=len(text_content) if text_content else 0)
                return

            # Create document record
            doc_id = self.generate_doc_id(url)
            timestamp = datetime.utcnow().isoformat()

            document = {
                'id': doc_id,
                'url': url,
                'domain': urlparse(url).netloc,
                'title': title,
                'content': text_content,
                'content_length': len(text_content),
                'links_found': len(links),
                'depth': response.meta.get('depth', 0),
                'status_code': response.status,
                'timestamp': timestamp,
                'content_hash': self.hash_content(text_content),
                'links': links[:100]  # Limit links to prevent explosion
            }

            self.crawled_data.append(document)
            CRAWLED_PAGES.inc()

            logger.info("Crawled page",
                       url=url,
                       title=title[:50],
                       content_length=len(text_content),
                       links_found=len(links))

            # Save periodically
            if len(self.crawled_data) % 10 == 0:
                self.save_batch()

        except Exception as e:
            logger.error("Error parsing page", url=response.url, error=str(e))

    def extract_title(self, response) -> str:
        """Extract page title"""
        title = response.css('title::text').get()
        if title:
            return title.strip()

        # Fallback: look for h1
        h1 = response.css('h1::text').get()
        if h1:
            return h1.strip()

        return "No Title"

    def extract_text_content(self, response) -> str:
        """Extract clean text content from page"""
        # Extract text from main content areas, excluding unwanted elements
        selectors = [
            'main',
            'article',
            '.content',
            '#content',
            '.main-content',
            'body'
        ]

        text_parts = []
        for selector in selectors:
            # Get all text excluding script, style, nav, header, footer, aside
            elements = response.css(f'{selector} *:not(script):not(style):not(nav):not(header):not(footer):not(aside)::text').getall()
            if elements:
                text = ' '.join(elements).strip()
                # Clean up whitespace
                text = re.sub(r'\s+', ' ', text)
                text = re.sub(r'\n+', '\n', text)
                if len(text) > 200:  # Minimum content length
                    text_parts.append(text)
                    break

        return text_parts[0] if text_parts else ""

    def extract_links(self, response) -> List[str]:
        """Extract all links from the page"""
        links = []
        for link in response.css('a::attr(href)').getall():
            try:
                absolute_url = urljoin(response.url, link)
                parsed = urlparse(absolute_url)

                # Filter out fragments and non-http(s)
                if parsed.scheme in ['http', 'https'] and not parsed.fragment:
                    links.append(absolute_url)
            except:
                continue

        return list(set(links))  # Remove duplicates

    def generate_doc_id(self, url: str) -> str:
        """Generate unique document ID from URL"""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = str(int(time.time()))
        return f"crawl_{timestamp}_{url_hash}"

    def hash_content(self, content: str) -> str:
        """Generate content hash for deduplication"""
        return hashlib.sha256(content.encode()).hexdigest()

    def save_batch(self):
        """Save current batch of crawled data"""
        if not self.crawled_data:
            return

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"crawl_batch_{timestamp}.jsonl"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            for doc in self.crawled_data:
                f.write(json.dumps(doc, ensure_ascii=False) + '\n')

        logger.info("Saved crawl batch",
                   filename=filename,
                   documents=len(self.crawled_data))

        self.crawled_data.clear()

    def closed(self, reason):
        """Called when spider closes"""
        # Save any remaining data
        self.save_batch()
        logger.info("Crawler finished", reason=reason, total_pages=len(self.visited_urls))


def run_crawler(start_url: str, max_depth: int = 3, output_dir: str = 'dataset/raw'):
    """Run the crawler with given parameters"""

    # Parse start URL to get domain
    parsed = urlparse(start_url)
    allowed_domains = [parsed.netloc]

    # Initialize crawler process
    process = CrawlerProcess({
        'USER_AGENT': 'ProfessionalDatasetCrawler/1.0 (+https://github.com/dataset-crawler)',
        'ROBOTSTXT_OBEY': True,
        'DOWNLOAD_DELAY': 1,  # Be respectful
        'CONCURRENT_REQUESTS': 4,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1,
        'AUTOTHROTTLE_MAX_DELAY': 10,
        'HTTPCACHE_ENABLED': False,  # Disable cache for testing
        'HTTPCACHE_EXPIRATION_SECS': 3600,
        'LOG_LEVEL': 'DEBUG',  # Enable debug logging
    })

    # Add crawler to process
    process.crawl(
        ProfessionalCrawler,
        start_urls=[start_url],
        allowed_domains=allowed_domains,
        max_depth=max_depth,
        output_dir=output_dir
    )

    # Start crawling
    process.start()


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python crawler.py <start_url> [max_depth] [output_dir]")
        sys.exit(1)

    start_url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    output_dir = sys.argv[3] if len(sys.argv) > 3 else 'dataset/raw'

    run_crawler(start_url, max_depth, output_dir)

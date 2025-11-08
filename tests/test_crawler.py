"""
Tests for the crawler component
"""
import pytest
from unittest.mock import Mock, patch
from crawler.crawler import extract_root_domain


class TestDomainExtraction:
    """Test domain extraction functionality"""

    def test_extract_root_domain_standard(self):
        """Test standard domain extraction"""
        assert extract_root_domain("example.com") == "example.com"
        assert extract_root_domain("sub.example.com") == "example.com"
        assert extract_root_domain("docs.kubernetes.io") == "kubernetes.io"

    def test_extract_root_domain_special_tlds(self):
        """Test domains with special TLDs"""
        assert extract_root_domain("example.co.uk") == "example.co.uk"
        assert extract_root_domain("sub.example.co.uk") == "example.co.uk"
        assert extract_root_domain("docs.example.com.au") == "example.com.au"

    def test_extract_root_domain_edge_cases(self):
        """Test edge cases"""
        assert extract_root_domain("localhost") == "localhost"
        assert extract_root_domain("example.org") == "example.org"


class TestCrawlerIntegration:
    """Test crawler integration (mocked)"""

    @patch('scrapy.Spider')
    def test_crawler_initialization(self, mock_spider):
        """Test that crawler can be initialized"""
        # This is a basic smoke test - in real scenario we'd test actual crawling
        from crawler.crawler import DatasetCrawler

        # Test that the class can be imported and has expected attributes
        assert hasattr(DatasetCrawler, 'name')
        assert DatasetCrawler.name == 'professional_crawler'

    def test_crawler_imports(self):
        """Test that all crawler components can be imported"""
        try:
            from crawler.crawler import DatasetCrawler, run_crawler
            from crawler.worker import main
            # If we get here without exceptions, imports work
            assert True
        except ImportError:
            pytest.fail("Failed to import crawler components")

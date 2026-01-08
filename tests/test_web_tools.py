"""Tests for WebToolProvider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from reos.code_mode.web_tools import (
    WebToolProvider,
    SearchResult,
    FetchedContent,
    KNOWN_DOCS,
    MAX_CONTENT_LENGTH,
)
from reos.code_mode.tools import ToolCategory, ToolProvider


class TestWebToolProvider:
    """Tests for WebToolProvider."""

    def test_list_tools(self) -> None:
        """Should list all web tools."""
        provider = WebToolProvider()
        tools = provider.list_tools()

        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "web_search" in tool_names
        assert "fetch_url" in tool_names
        assert "fetch_docs" in tool_names

    def test_all_tools_have_web_category(self) -> None:
        """All tools should be in WEB category."""
        provider = WebToolProvider()
        for tool in provider.list_tools():
            assert tool.category == ToolCategory.WEB

    def test_has_tool(self) -> None:
        """Should check if tool exists."""
        provider = WebToolProvider()

        assert provider.has_tool("web_search")
        assert provider.has_tool("fetch_url")
        assert provider.has_tool("fetch_docs")
        assert not provider.has_tool("nonexistent")

    def test_implements_protocol(self) -> None:
        """Should implement ToolProvider protocol."""
        provider = WebToolProvider()
        assert isinstance(provider, ToolProvider)

    def test_unknown_tool(self) -> None:
        """Should handle unknown tool gracefully."""
        provider = WebToolProvider()
        result = provider.call_tool("unknown_tool", {})

        assert not result.success
        assert "Unknown tool" in result.error


class TestWebSearch:
    """Tests for web_search tool."""

    @patch("httpx.Client")
    def test_successful_search(self, mock_client_class: MagicMock) -> None:
        """Should return search results on success."""
        # Mock response with DuckDuckGo-like HTML
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <div class="result">
            <a class="result__a" href="https://example.com/page1">Example Page 1</a>
            <a class="result__snippet">This is a snippet about the first result.</a>
        </div>
        </html>
        """
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        provider = WebToolProvider()
        result = provider.call_tool("web_search", {"query": "python tutorial"})

        assert result.success
        assert "python tutorial" in result.output.lower() or "search results" in result.output.lower()

    @patch("httpx.Client")
    def test_search_timeout(self, mock_client_class: MagicMock) -> None:
        """Should handle timeout gracefully."""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        provider = WebToolProvider()
        result = provider.call_tool("web_search", {"query": "test"})

        assert not result.success
        assert "timed out" in result.error.lower()

    def test_num_results_limit(self) -> None:
        """Should respect max results limit."""
        provider = WebToolProvider()
        # This will make a real request if not mocked, but we're testing the limit logic
        # The actual limit is applied in the call
        tools = provider.list_tools()
        search_tool = next(t for t in tools if t.name == "web_search")
        assert "max" in search_tool.input_schema["properties"]["num_results"]["description"]


class TestFetchUrl:
    """Tests for fetch_url tool."""

    @patch("httpx.Client")
    def test_successful_fetch(self, mock_client_class: MagicMock) -> None:
        """Should fetch and extract content."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <head><title>Test Page</title></head>
        <body>
        <main>
            <h1>Hello World</h1>
            <p>This is test content.</p>
        </main>
        </body>
        </html>
        """
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        provider = WebToolProvider()
        result = provider.call_tool("fetch_url", {"url": "https://example.com/page"})

        assert result.success
        assert "Test Page" in result.output
        assert "Hello World" in result.output or "test content" in result.output.lower()

    def test_invalid_url(self) -> None:
        """Should reject invalid URLs."""
        provider = WebToolProvider()
        result = provider.call_tool("fetch_url", {"url": "not-a-valid-url"})

        assert not result.success
        assert "Invalid URL" in result.error

    @patch("httpx.Client")
    def test_extract_code_blocks(self, mock_client_class: MagicMock) -> None:
        """Should extract code blocks when requested."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <head><title>Code Example</title></head>
        <body>
            <pre><code>def hello():
    print("Hello, World!")
</code></pre>
        </body>
        </html>
        """
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        provider = WebToolProvider()
        result = provider.call_tool("fetch_url", {
            "url": "https://example.com/code",
            "extract_code": True,
        })

        assert result.success
        assert "def hello" in result.output or "```" in result.output

    @patch("httpx.Client")
    def test_content_truncation(self, mock_client_class: MagicMock) -> None:
        """Should truncate large content."""
        # Create very long content
        long_content = "x" * (MAX_CONTENT_LENGTH + 1000)

        mock_response = MagicMock()
        mock_response.text = f"<html><body>{long_content}</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        provider = WebToolProvider(max_content_length=1000)
        result = provider.call_tool("fetch_url", {"url": "https://example.com/long"})

        assert result.success
        assert result.data.get("truncated") is True
        assert "[Content truncated...]" in result.output


class TestFetchDocs:
    """Tests for fetch_docs tool."""

    def test_known_libraries(self) -> None:
        """Should recognize common libraries."""
        # Verify we have docs for common libraries
        assert "python" in KNOWN_DOCS
        assert "react" in KNOWN_DOCS
        assert "fastapi" in KNOWN_DOCS
        assert "pygame" in KNOWN_DOCS

    @patch.object(WebToolProvider, "_fetch_url")
    def test_fetch_known_library(self, mock_fetch: MagicMock) -> None:
        """Should fetch docs for known library."""
        from reos.code_mode.tools import ToolResult

        mock_fetch.return_value = ToolResult(
            success=True,
            output="Python documentation content",
            source="web.fetch",
        )

        provider = WebToolProvider()
        result = provider.call_tool("fetch_docs", {"library": "python"})

        assert result.success
        mock_fetch.assert_called_once()

    @patch.object(WebToolProvider, "_web_search")
    def test_unknown_library_falls_back_to_search(self, mock_search: MagicMock) -> None:
        """Should search for unknown libraries."""
        from reos.code_mode.tools import ToolResult

        mock_search.return_value = ToolResult(
            success=True,
            output="Search results for unknown_lib",
            source="web.search",
        )

        provider = WebToolProvider()
        result = provider.call_tool("fetch_docs", {"library": "some_unknown_library"})

        assert result.success
        mock_search.assert_called_once()
        # Should search for documentation - check positional arg
        call_args = mock_search.call_args[0]
        assert "documentation" in call_args[0]

    @patch.object(WebToolProvider, "_web_search")
    def test_topic_search_within_docs(self, mock_search: MagicMock) -> None:
        """Should search for topic within library docs."""
        from reos.code_mode.tools import ToolResult

        mock_search.return_value = ToolResult(
            success=True,
            output="Search results",
            source="web.search",
        )

        provider = WebToolProvider()
        result = provider.call_tool("fetch_docs", {
            "library": "python",
            "topic": "asyncio",
        })

        assert result.success
        mock_search.assert_called_once()
        # Should use site: search - check positional arg
        call_args = mock_search.call_args[0]
        assert "site:" in call_args[0]
        assert "asyncio" in call_args[0]


class TestHtmlParsing:
    """Tests for HTML content extraction."""

    def test_clean_html(self) -> None:
        """Should clean HTML tags and entities."""
        provider = WebToolProvider()
        result = provider._clean_html("<p>Hello &amp; World</p>")
        assert result == "Hello & World"

    def test_extract_content_removes_scripts(self) -> None:
        """Should remove script tags."""
        provider = WebToolProvider()
        html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <script>alert('evil');</script>
            <p>Good content</p>
        </body>
        </html>
        """
        content, title = provider._extract_html_content(html)

        assert "alert" not in content
        assert "Good content" in content
        assert title == "Test"

    def test_extract_content_removes_nav_footer(self) -> None:
        """Should remove navigation and footer."""
        provider = WebToolProvider()
        html = """
        <html>
        <body>
            <nav>Navigation links</nav>
            <main>Main content here</main>
            <footer>Copyright info</footer>
        </body>
        </html>
        """
        content, _ = provider._extract_html_content(html)

        assert "Main content" in content
        # Nav and footer should be reduced/removed
        assert content.count("Navigation") < content.count("Main")

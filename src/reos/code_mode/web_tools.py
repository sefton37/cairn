"""Web Tool Provider for Code Mode.

Provides web-based tools that RIVA can use to gather information
when uncertain or debugging:

1. Web Search - Find solutions to errors, library usage examples
2. Fetch URL - Get documentation, API references, Stack Overflow answers
3. Fetch API Docs - Targeted documentation fetching for common libraries

These tools help RIVA when it:
- Encounters unfamiliar APIs
- Needs to debug errors it hasn't seen before
- Wants to verify best practices

Security Notes:
- All requests have timeouts
- Content is truncated to avoid context overflow
- Only text content is extracted (no scripts, etc.)
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from .tools import ToolCategory, ToolInfo, ToolResult

logger = logging.getLogger(__name__)

# Maximum content size to return (prevent context overflow)
MAX_CONTENT_LENGTH = 15000
MAX_SEARCH_RESULTS = 5

# Common documentation URLs for popular libraries
KNOWN_DOCS = {
    # Python
    "python": "https://docs.python.org/3/",
    "requests": "https://requests.readthedocs.io/en/latest/",
    "flask": "https://flask.palletsprojects.com/",
    "django": "https://docs.djangoproject.com/",
    "fastapi": "https://fastapi.tiangolo.com/",
    "pytest": "https://docs.pytest.org/",
    "numpy": "https://numpy.org/doc/stable/",
    "pandas": "https://pandas.pydata.org/docs/",
    "pygame": "https://www.pygame.org/docs/",
    "sqlalchemy": "https://docs.sqlalchemy.org/",
    "pydantic": "https://docs.pydantic.dev/latest/",
    # JavaScript/TypeScript
    "react": "https://react.dev/reference/react",
    "nextjs": "https://nextjs.org/docs",
    "typescript": "https://www.typescriptlang.org/docs/",
    "node": "https://nodejs.org/docs/latest/api/",
    # Rust
    "rust": "https://doc.rust-lang.org/std/",
    "tokio": "https://docs.rs/tokio/latest/tokio/",
    "serde": "https://serde.rs/",
}


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str


@dataclass
class FetchedContent:
    """Content fetched from a URL."""

    url: str
    title: str
    content: str
    content_type: str = "text/html"
    truncated: bool = False


class WebToolProvider:
    """Tool provider for web-based information gathering.

    Provides tools for searching the web and fetching documentation
    to help RIVA when it's uncertain or debugging.

    Usage:
        provider = WebToolProvider()
        result = provider.call_tool("web_search", {"query": "python asyncio tutorial"})
    """

    def __init__(
        self,
        timeout: float = 10.0,
        max_content_length: int = MAX_CONTENT_LENGTH,
    ) -> None:
        self._timeout = timeout
        self._max_content_length = max_content_length
        self._tools = self._build_tool_list()

    def _build_tool_list(self) -> list[ToolInfo]:
        """Build list of available web tools."""
        return [
            ToolInfo(
                name="web_search",
                description=(
                    "Search the web for information. Use for finding solutions to errors, "
                    "library documentation, code examples, and best practices."
                ),
                category=ToolCategory.WEB,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (be specific, include language/library names)",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": f"Number of results (default: 3, max: {MAX_SEARCH_RESULTS})",
                        },
                    },
                    "required": ["query"],
                },
                use_when="need to find solutions, documentation, or examples",
            ),
            ToolInfo(
                name="fetch_url",
                description=(
                    "Fetch and extract text content from a URL. Use for reading documentation, "
                    "Stack Overflow answers, or blog posts."
                ),
                category=ToolCategory.WEB,
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch"},
                        "extract_code": {
                            "type": "boolean",
                            "description": "Focus on extracting code blocks (default: false)",
                        },
                    },
                    "required": ["url"],
                },
                use_when="need to read specific documentation or answers",
            ),
            ToolInfo(
                name="fetch_docs",
                description=(
                    "Fetch documentation for a known library. Faster than general search "
                    "for common libraries like Python, React, FastAPI, etc."
                ),
                category=ToolCategory.WEB,
                input_schema={
                    "type": "object",
                    "properties": {
                        "library": {
                            "type": "string",
                            "description": f"Library name. Known: {', '.join(sorted(KNOWN_DOCS.keys()))}",
                        },
                        "topic": {
                            "type": "string",
                            "description": "Specific topic to search within docs (optional)",
                        },
                    },
                    "required": ["library"],
                },
                use_when="need documentation for a specific well-known library",
            ),
        ]

    def list_tools(self) -> list[ToolInfo]:
        """List all web tools."""
        return self._tools.copy()

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return any(t.name == name for t in self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call a web tool."""
        try:
            if name == "web_search":
                return self._web_search(
                    query=arguments["query"],
                    num_results=min(
                        arguments.get("num_results", 3),
                        MAX_SEARCH_RESULTS,
                    ),
                )

            elif name == "fetch_url":
                return self._fetch_url(
                    url=arguments["url"],
                    extract_code=arguments.get("extract_code", False),
                )

            elif name == "fetch_docs":
                return self._fetch_docs(
                    library=arguments["library"],
                    topic=arguments.get("topic"),
                )

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown tool: {name}",
                    source="web",
                )

        except Exception as e:
            logger.exception("Web tool call failed: %s", name)
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                source=f"web.{name}",
            )

    def _web_search(self, query: str, num_results: int = 3) -> ToolResult:
        """Search the web using DuckDuckGo HTML interface.

        Uses DuckDuckGo's HTML interface which doesn't require an API key.
        Falls back gracefully if search fails.
        """
        import httpx

        try:
            # Use DuckDuckGo HTML interface
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                response = client.get(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; ReOS/1.0; +https://github.com/sefton37/ReOS)",
                    },
                )
                response.raise_for_status()

            # Parse results from HTML
            results = self._parse_ddg_results(response.text, num_results)

            if not results:
                return ToolResult(
                    success=True,
                    output="No search results found. Try a different query.",
                    data={"results": []},
                    source="web.search.duckduckgo",
                    confidence=0.5,
                )

            # Format results for LLM consumption
            output_lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. {r.title}")
                output_lines.append(f"   URL: {r.url}")
                output_lines.append(f"   {r.snippet}\n")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={"results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results]},
                source="web.search.duckduckgo",
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output="",
                error="Search timed out. Try again or use a more specific query.",
                source="web.search",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Search failed: {str(e)}",
                source="web.search",
            )

    def _parse_ddg_results(self, html_content: str, max_results: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML search results."""
        results = []

        # Find result blocks - DuckDuckGo uses class="result"
        result_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>([^<]*(?:<[^>]*>[^<]*)*)</a>',
            re.DOTALL | re.IGNORECASE,
        )

        # Simpler fallback pattern
        link_pattern = re.compile(
            r'<a[^>]*class="[^"]*result[^"]*"[^>]*href="([^"]*)"[^>]*>.*?<.*?>([^<]+)</.*?</a>',
            re.DOTALL | re.IGNORECASE,
        )

        for match in result_pattern.finditer(html_content):
            if len(results) >= max_results:
                break

            url = match.group(1)
            title = self._clean_html(match.group(2))
            snippet = self._clean_html(match.group(3))

            # Skip DuckDuckGo internal links
            if "duckduckgo.com" in url:
                continue

            # Extract actual URL from DDG redirect
            if "/l/?uddg=" in url:
                try:
                    from urllib.parse import parse_qs, urlparse as parse_url
                    parsed = parse_qs(parse_url(url).query)
                    url = parsed.get("uddg", [url])[0]
                except Exception:
                    pass

            if title and url:
                results.append(SearchResult(
                    title=title.strip(),
                    url=url,
                    snippet=snippet.strip()[:300] if snippet else "",
                ))

        return results

    def _fetch_url(self, url: str, extract_code: bool = False) -> ToolResult:
        """Fetch and extract content from a URL."""
        import httpx

        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid URL: {url}",
                    source="web.fetch",
                )

            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; ReOS/1.0; +https://github.com/sefton37/ReOS)",
                        "Accept": "text/html,application/xhtml+xml,text/plain",
                    },
                )
                response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            # Handle different content types
            if "application/json" in content_type:
                content = response.text
                title = "JSON Response"
            elif "text/plain" in content_type:
                content = response.text
                title = "Plain Text"
            else:
                # HTML - extract text content
                content, title = self._extract_html_content(
                    response.text,
                    extract_code=extract_code,
                )

            # Truncate if needed
            truncated = False
            if len(content) > self._max_content_length:
                content = content[: self._max_content_length]
                content += "\n\n[Content truncated...]"
                truncated = True

            return ToolResult(
                success=True,
                output=f"# {title}\n\nURL: {url}\n\n{content}",
                data={
                    "url": url,
                    "title": title,
                    "truncated": truncated,
                    "content_length": len(content),
                },
                source="web.fetch",
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out for: {url}",
                source="web.fetch",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"HTTP {e.response.status_code} for: {url}",
                source="web.fetch",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Fetch failed: {str(e)}",
                source="web.fetch",
            )

    def _fetch_docs(self, library: str, topic: str | None = None) -> ToolResult:
        """Fetch documentation for a known library."""
        library_lower = library.lower()

        if library_lower not in KNOWN_DOCS:
            # Try a web search instead
            query = f"{library} documentation"
            if topic:
                query += f" {topic}"
            return self._web_search(query, num_results=3)

        base_url = KNOWN_DOCS[library_lower]

        if topic:
            # Search within the docs
            query = f"site:{urlparse(base_url).netloc} {topic}"
            return self._web_search(query, num_results=3)
        else:
            # Fetch the main docs page
            return self._fetch_url(base_url)

    def _extract_html_content(
        self,
        html_content: str,
        extract_code: bool = False,
    ) -> tuple[str, str]:
        """Extract readable text content from HTML.

        Returns (content, title) tuple.
        """
        # Extract title
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
        title = self._clean_html(title_match.group(1)) if title_match else "Untitled"

        # Remove script and style tags
        content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r"<nav[^>]*>.*?</nav>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r"<header[^>]*>.*?</header>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r"<footer[^>]*>.*?</footer>", "", content, flags=re.DOTALL | re.IGNORECASE)

        if extract_code:
            # Focus on code blocks
            code_blocks = []

            # Find <pre><code> blocks
            pre_pattern = re.compile(r"<pre[^>]*>.*?<code[^>]*>(.*?)</code>.*?</pre>", re.DOTALL | re.IGNORECASE)
            for match in pre_pattern.finditer(content):
                code = self._clean_html(match.group(1))
                if code.strip():
                    code_blocks.append(f"```\n{code}\n```")

            # Find standalone <code> blocks (inline code)
            code_pattern = re.compile(r"<code[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE)
            for match in code_pattern.finditer(content):
                code = self._clean_html(match.group(1))
                if code.strip() and len(code) > 20:  # Skip tiny inline code
                    code_blocks.append(f"`{code}`")

            if code_blocks:
                return "\n\n".join(code_blocks[:20]), title  # Limit code blocks

        # Extract main content areas
        main_content = content

        # Try to find main content area
        for tag in ["main", "article", "div[class*='content']", "div[class*='body']"]:
            pattern = re.compile(f"<{tag.split('[')[0]}[^>]*>(.*?)</{tag.split('[')[0]}>", re.DOTALL | re.IGNORECASE)
            match = pattern.search(content)
            if match and len(match.group(1)) > 500:
                main_content = match.group(1)
                break

        # Clean HTML tags
        text = self._clean_html(main_content)

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        return text.strip(), title

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities
        text = html.unescape(text)
        # Clean whitespace
        text = " ".join(text.split())
        return text

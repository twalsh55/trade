from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx


@dataclass(frozen=True)
class DuckDuckGoSearchResult:
    title: str
    snippet: str
    url: str
    published_at: datetime


class DuckDuckGoSiteSearchError(RuntimeError):
    """Raised when public DuckDuckGo site search fails."""


class DuckDuckGoSiteSearch:
    SEARCH_URL = "https://html.duckduckgo.com/html/"

    def __init__(
        self,
        site_domains: tuple[str, ...],
        user_agent: str,
        timeout_seconds: float = 20.0,
        now: callable | None = None,
    ) -> None:
        self.site_domains = site_domains
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.now = now or (lambda: datetime.now(tz=UTC))

    def search(self, query: str, limit: int) -> list[DuckDuckGoSearchResult]:
        search_query = self._build_query(query)
        try:
            response = httpx.get(
                self.SEARCH_URL,
                params={"q": search_query},
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DuckDuckGoSiteSearchError("Unable to load public site search results.") from exc

        parser = _DuckDuckGoResultParser(allowed_domains=self.site_domains, limit=limit)
        parser.feed(response.text)
        parser.close()
        return [
            DuckDuckGoSearchResult(
                title=item["title"],
                snippet=item["snippet"],
                url=item["url"],
                published_at=self.now(),
            )
            for item in parser.results
        ]

    def _build_query(self, query: str) -> str:
        if not self.site_domains:
            return query
        site_filters = " OR ".join(f"site:{domain}" for domain in self.site_domains)
        return f"{query} ({site_filters})"


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self, allowed_domains: tuple[str, ...], limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.allowed_domains = tuple(domain.lower() for domain in allowed_domains)
        self.limit = limit
        self.results: list[dict[str, str]] = []
        self._capture_title = False
        self._capture_snippet = False
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._pending_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = attr_map.get("class", "") or ""

        if tag == "a" and "result__a" in classes and len(self.results) < self.limit:
            self._capture_title = True
            self._title_parts = []
            self._pending_href = _normalize_result_url(attr_map.get("href", "") or "")
            return

        if "result__snippet" in classes and self.results:
            self._capture_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
            title = " ".join(part.strip() for part in self._title_parts if part.strip()).strip()
            if title and self._pending_href and _url_matches_allowed_domains(self._pending_href, self.allowed_domains):
                self.results.append({"title": title, "snippet": "", "url": self._pending_href})
            self._pending_href = ""
            self._title_parts = []
            return

        if self._capture_snippet and tag in {"a", "div", "span"}:
            self._capture_snippet = False
            snippet = " ".join(part.strip() for part in self._snippet_parts if part.strip()).strip()
            if snippet and self.results and not self.results[-1]["snippet"]:
                self.results[-1]["snippet"] = snippet
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)


def _normalize_result_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return href


def _url_matches_allowed_domains(url: str, allowed_domains: tuple[str, ...]) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False
    if not allowed_domains:
        return True
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)

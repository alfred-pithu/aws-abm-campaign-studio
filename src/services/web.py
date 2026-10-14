"""Stdlib page fetch for product onboarding. Failures are warnings, not crashes."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 200_000
TIMEOUT_SECONDS = 8
_SKIP_TAGS = {"script", "style", "noscript", "template"}


@dataclass(frozen=True)
class PageFetch:
    text: str = ""
    error: str = ""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = unescape(data).strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return " ".join(self._parts)


def _strip_tags(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return " ".join(html.split())
    return parser.text()


def fetch_page(url: str, *, timeout: int = TIMEOUT_SECONDS, max_bytes: int = MAX_BYTES) -> PageFetch:
    raw_url = (url or "").strip()
    if not raw_url:
        return PageFetch(error="No URL provided.")
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return PageFetch(error="Only http(s) URLs are supported.")
    request = Request(
        raw_url,
        headers={"User-Agent": "AWS-ISV-Campaign-Studio/0.1 (product-onboarding)"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above
            content_type = (response.headers.get_content_type() or "").lower()
            chunks: list[bytes] = []
            total = 0
            while True:
                piece = response.read(min(8192, max_bytes - total + 1))
                if not piece:
                    break
                total += len(piece)
                if total > max_bytes:
                    return PageFetch(error="The page is too large to fetch.")
                chunks.append(piece)
    except TimeoutError:
        return PageFetch(error="The page timed out.")
    except URLError as exc:
        return PageFetch(error=f"Could not fetch the page: {exc.reason}")
    except Exception:
        return PageFetch(error="Could not fetch the page.")

    html = b"".join(chunks).decode("utf-8", errors="replace")
    if content_type and "html" not in content_type and "text" not in content_type:
        return PageFetch(error="The URL did not return readable page text.")
    text = _strip_tags(html)
    if not text:
        return PageFetch(error="The page did not contain readable text.")
    return PageFetch(text=text)

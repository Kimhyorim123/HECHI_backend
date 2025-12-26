import os
import re
from typing import Any, Dict, List, Optional
import httpx
from datetime import date

from app.core.config import get_settings


def _extract_isbn(industry_identifiers: List[Dict[str, Any]]) -> Optional[str]:
    candidates = {}
    for item in industry_identifiers or []:
        t = item.get("type")
        idv = item.get("identifier")
        if not (t and idv):
            continue
        digits = re.sub(r"[^0-9Xx]", "", idv)
        if len(digits) in (10, 13):
            candidates[t] = digits.upper()
    return candidates.get("ISBN_13") or candidates.get("ISBN_10")


def _parse_published_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip()
    # Patterns: YYYY, YYYY-MM, YYYY-MM-DD
    if re.fullmatch(r"\d{4}", raw):
        return date(int(raw), 1, 1)
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        y, m = raw.split("-")
        return date(int(y), int(m), 1)
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _normalize_category(categories: List[str]) -> Optional[str]:
    if not categories:
        return None
    # 첫 항목 사용
    return categories[0]


class GoogleBooksClient:
    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.api_key:
            params["key"] = self.api_key
        with httpx.Client(timeout=10.0) as client:
            r = client.get(self.BASE_URL, params=params)
            r.raise_for_status()
            return r.json()

    def by_isbn(self, isbn: str) -> List[Dict[str, Any]]:
        data = self._request({"q": f"isbn:{isbn}"})
        return data.get("items", [])

    def by_query(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        data = self._request({"q": query, "maxResults": max_results})
        return data.get("items", [])

    def by_query_paged(self, query: str, start_index: int, max_results: int) -> List[Dict[str, Any]]:
        data = self._request({"q": query, "startIndex": start_index, "maxResults": max_results})
        return data.get("items", [])


def map_volume_to_book_fields(volume: Dict[str, Any]) -> Dict[str, Any]:
    info = volume.get("volumeInfo", {})
    isbn = _extract_isbn(info.get("industryIdentifiers", []))
    pub_date = _parse_published_date(info.get("publishedDate"))
    image_links = info.get("imageLinks", {}) or {}
    categories = info.get("categories", []) or []
    return {
        "isbn": isbn,
        "title": info.get("title"),
        "publisher": info.get("publisher"),
        "published_date": pub_date,
        "language": info.get("language"),
        "category": _normalize_category(categories),
        "categories": categories,
        "total_pages": info.get("pageCount"),
        "authors": info.get("authors", []) or [],
        "thumbnail": image_links.get("thumbnail"),
        "small_thumbnail": image_links.get("smallThumbnail"),
        "google_rating": info.get("averageRating"),
        "google_ratings_count": info.get("ratingsCount"),
    }


def get_client() -> GoogleBooksClient:
    settings = get_settings()
    return GoogleBooksClient(settings.google_books_api_key)
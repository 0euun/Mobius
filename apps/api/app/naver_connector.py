# NAVER Search API 결과를 확산 신호 이벤트로 정규화

import html
import json
import os
import re
import hashlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .privacy import mask_text

BASE_URL = "https://naverapihub.apigw.ntruss.com/search/v1"
ALLOWED_SOURCES = {"news", "blog", "cafearticle", "kin", "webkr"}


def status() -> dict:
    return {"provider": "naver_search", "configured": bool(os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET")), "mode": "official_api", "scope": "search result signals"}


def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def normalize_date(value: str | None) -> str:
    if not value:
        return datetime.now(UTC).isoformat()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}T00:00:00+00:00"
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


def _search(source: str, query: str, display: int) -> dict:
    if source not in ALLOWED_SOURCES: raise ValueError(f"지원하지 않는 NAVER 검색 소스: {source}")
    client_id, client_secret = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret: raise RuntimeError("NAVER_CLIENT_ID/SECRET 설정이 필요합니다.")
    request = Request(f"{BASE_URL}/{source}?{urlencode({'query': query, 'display': display, 'sort': 'date'})}", headers={"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret})
    with urlopen(request, timeout=15) as response: return json.loads(response.read())


def collect(query: str, sources: list[str], display: int, target_id: str) -> list[dict]:
    events = []
    for source in sources:
        for index, item in enumerate(_search(source, query, display).get("items", [])):
            title, text = _clean(item.get("title", "")), _clean(item.get("description", ""))
            if not (title or text): continue
            date = normalize_date(item.get("pubDate") or item.get("postdate"))
            url = item.get("originallink") or item.get("link", "")
            identity = hashlib.sha256((url or title + str(index)).encode()).hexdigest()[:24]
            events.append({"event_id": f"naver:{source}:{identity}", "occurred_at": date, "platform": f"naver_{source}", "author_ref": "naver-search-result", "target_ref": target_id, "text": mask_text(f"{title} {text}".strip()), "hashtags": [], "likes": 0, "shares": 0, "comments": 0, "source_url": url})
    return events

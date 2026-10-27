"""수집 원본(RawItem) → incidents 행 변환."""
import hashlib
import json
from datetime import date

from . import region

FIELDS = ("posted_date", "occurred_at", "sido", "sigungu", "industry", "accident_type",
          "deaths", "injuries", "title", "summary", "source_url")


def content_id(*parts):
    return hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:20]


def to_incident(item):
    """item: dict(source_id, title, body, posted_date, url, 그리고 이미 구조화된 값이 있으면 같은 키로)."""
    title = (item.get("title") or "").strip()
    body = (item.get("body") or item.get("summary") or "").strip()
    text = f"{title} {body}"

    sido, sgg = item.get("sido"), item.get("sigungu")
    if not sido:
        sido, sgg2 = region.extract_region(text)
        sgg = sgg or sgg2
    elif sido not in region.SIDO_LIST:
        sido, _ = region.extract_region(sido)

    dead = item.get("deaths")
    inj = item.get("injuries")
    if dead in (None, "") or inj in (None, ""):
        d2, i2 = region.extract_people(text)
        dead = d2 if dead in (None, "") else dead
        inj = i2 if inj in (None, "") else inj

    posted = item.get("posted_date") or date.today().isoformat()
    posted = region.extract_datetime(posted) or posted
    posted = posted[:10]
    occurred = item.get("occurred_at") or region.extract_datetime(body) or None

    row = {
        "posted_date": posted,
        "occurred_at": occurred,
        "sido": sido,
        "sigungu": sgg,
        "industry": item.get("industry") or region.extract_industry(text),
        "accident_type": item.get("accident_type") or region.extract_type(text),
        "deaths": int(dead or 0),
        "injuries": int(inj or 0),
        "title": title or None,
        "summary": body[:2000] or None,
        "source_url": item.get("url") or item.get("source_url"),
    }
    sid = item.get("source_id") or content_id(row["posted_date"], title, body)
    return str(sid), row, json.dumps(item, ensure_ascii=False, default=str)[:20000]

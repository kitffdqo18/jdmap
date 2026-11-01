"""안전보건공단 '중대재해 사이렌' 수집 어댑터 (설정 파일 방식).

사이렌 화면은 스크립트로 목록을 불러오므로, 실제 데이터 주소는 브라우저 개발자도구
(Network 탭 → Fetch/XHR)에서 확인해 collector/siren_config.json 에 적는다.
README '사이렌 연동 설정' 절차 참고. 코드 수정 없이 설정만 바꾸면 된다.

지원 방식
- mode "json": 목록 API가 JSON을 돌려주는 경우 (가장 흔함)
- mode "html": 서버가 HTML 목록을 내려주는 경우 (CSS 선택자로 추출)
"""
import json
import os
import re
import time

import requests

CONFIG_PATH = os.environ.get("SIREN_CONFIG", os.path.join(os.path.dirname(__file__), "..", "siren_config.json"))


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dig(obj, path):
    """'data.list' 같은 점 경로로 값 꺼내기. 숫자는 배열 인덱스."""
    if not path:
        return obj
    for key in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            obj = obj.get(key)
    return obj


def _session(cfg):
    s = requests.Session()
    s.headers.update({
        "User-Agent": cfg.get("user_agent") or "JDMAP-Collector/1.0 (+contact: admin)",
        "Accept": "application/json, text/html;q=0.9",
        **cfg.get("headers", {}),
    })
    return s


def _request(s, cfg, page):
    params = json.loads(json.dumps(cfg.get("params", {})).replace('"{page}"', str(page)).replace("{page}", str(page)))
    if cfg.get("method", "GET").upper() == "POST":
        if cfg.get("body_type", "json") == "form":
            r = s.post(cfg["list_url"], data=params, timeout=20)
        else:
            r = s.post(cfg["list_url"], json=params, timeout=20)
    else:
        r = s.get(cfg["list_url"], params=params, timeout=20)
    r.raise_for_status()
    return r


def fetch_json(cfg, session=None, known=None):
    """known: 이미 수집해 둔 게시물 번호 집합 (그림 글자 읽기를 다시 하지 않으려고)."""
    s = session or _session(cfg)
    m = cfg["json"]
    known = set(known or ())
    if m.get("image") and cfg.get("ocr"):
        from .. import ocr
        if not ocr.available():
            raise RuntimeError("그림 글자 읽기 프로그램(tesseract)이 없습니다. collect.yml 의 OCR 준비 단계를 확인하세요.")
    out = []
    for page in range(1, int(cfg.get("pages", 1)) + 1):
        data = _request(s, cfg, page).json()
        items = dig(data, m["items_path"]) or []
        for it in items:
            sid = dig(it, m["id"])
            if str(sid) in known:
                continue
            body = dig(it, m.get("body", "")) if m.get("body") else ""
            extra = {}
            # 본문이 그림 안에만 있으면 그림에서 글자를 읽는다 (OCR)
            if not body and m.get("image") and cfg.get("ocr"):
                from .. import ocr
                extra = ocr.read_poster(ocr.decode_data_url(dig(it, m["image"]) or "")) or {}
                body = extra.pop("body", "") or ""
                extra = {k: v for k, v in extra.items() if v}
                if not body:  # 다음 실행 때 다시 시도
                    print(f"  그림 글자 읽기 실패, 다음에 다시 시도: {sid} {dig(it, m.get('title', '')) or ''}")
                    continue
            # 목록에 본문이 없고 상세 API가 따로 있으면 상세 호출
            if not body and m.get("detail_url"):
                d = s.get(m["detail_url"].format(id=sid), timeout=20)
                d.raise_for_status()
                body = dig(d.json(), m.get("detail_body", "")) or ""
                time.sleep(float(cfg.get("delay_seconds", 1.0)))
            out.append({
                "source_id": str(sid),
                "title": dig(it, m.get("title", "")) or "",
                "body": _strip_html(body or ""),
                "posted_date": _title_date(dig(it, m.get("title", "")) or "") or str(dig(it, m.get("posted", "")) or ""),
                "url": (m.get("url_template") or "").format(id=sid) or cfg.get("public_url"),
                **extra,
            })
        time.sleep(float(cfg.get("delay_seconds", 1.0)))
    return out


def fetch_html(cfg, session=None):
    from bs4 import BeautifulSoup

    s = session or _session(cfg)
    h = cfg["html"]
    out = []
    for page in range(1, int(cfg.get("pages", 1)) + 1):
        soup = BeautifulSoup(_request(s, cfg, page).text, "html.parser")
        for node in soup.select(h["item_selector"]):
            link = node.select_one(h["link_selector"]) if h.get("link_selector") else None
            href = link.get("href") if link else None
            sid = node.get(h["id_attr"]) if h.get("id_attr") else None
            sid = sid or (link.get(h["link_id_attr"]) if link is not None and h.get("link_id_attr") else None) or href
            title = _text(node.select_one(h["title_selector"])) if h.get("title_selector") else _text(link)
            posted = _text(node.select_one(h["date_selector"])) if h.get("date_selector") else ""
            body = _text(node.select_one(h["body_selector"])) if h.get("body_selector") else ""
            if not body and href and h.get("detail_body_selector"):
                url = requests.compat.urljoin(cfg["list_url"], href)
                d = BeautifulSoup(s.get(url, timeout=20).text, "html.parser")
                body = _text(d.select_one(h["detail_body_selector"]))
                time.sleep(float(cfg.get("delay_seconds", 1.0)))
            out.append({
                "source_id": str(sid or title),
                "title": title,
                "body": body,
                "posted_date": posted,
                "url": requests.compat.urljoin(cfg["list_url"], href) if href else cfg.get("public_url"),
            })
        time.sleep(float(cfg.get("delay_seconds", 1.0)))
    return out


def _title_date(title):
    """'(261028)중대재해 발생 알림(1)' → '2026-10-28' (제목 앞 날짜가 실제 알림 날짜)."""
    m = re.match(r"\s*\((\d{2})(\d{2})(\d{2})\)", title or "")
    return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _text(node):
    return " ".join(node.get_text(" ").split()) if node is not None else ""


def _strip_html(s):
    if "<" not in s:
        return s.strip()
    from bs4 import BeautifulSoup
    return " ".join(BeautifulSoup(s, "html.parser").get_text(" ").split())


def fetch(cfg=None, session=None, known=None):
    cfg = cfg or load_config()
    if not cfg.get("enabled"):
        raise RuntimeError("siren_config.json 의 enabled 가 false 입니다. 데이터 주소를 확인해 설정한 뒤 true 로 바꾸세요.")
    if cfg.get("mode") == "html":
        return fetch_html(cfg, session)
    return fetch_json(cfg, session, known=known)

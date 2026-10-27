"""CSV 수동 등록. 사이렌 자동 수집이 막히거나 누락분을 보완할 때 사용.

양식: collector/incident_template.csv (엑셀에서 'CSV UTF-8'로 저장)
필수 열: 게시일, 사고개요   (나머지는 비우면 사고개요에서 자동 추출)
"""
import csv
import io

COLUMNS = {
    "게시일": "posted_date", "발생일시": "occurred_at", "시도": "sido", "시군구": "sigungu",
    "업종": "industry", "재해유형": "accident_type", "사망": "deaths", "부상": "injuries",
    "제목": "title", "사고개요": "body", "원문링크": "url", "고유번호": "source_id",
}


def parse(text):
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in ("게시일", "사고개요") if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"필수 열이 없습니다: {', '.join(missing)}. 양식 파일의 첫 줄(열 이름)을 그대로 사용하세요.")
    items = []
    for i, row in enumerate(reader, start=2):
        item = {COLUMNS[k]: (v or "").strip() for k, v in row.items() if k in COLUMNS}
        if not item.get("body") and not item.get("title"):
            continue
        for k in ("deaths", "injuries"):
            v = item.get(k, "")
            if v == "":
                item[k] = None
            else:
                try:
                    item[k] = int(float(v))
                except ValueError:
                    raise ValueError(f"{i}번째 줄: '{k}' 값은 숫자여야 합니다 (입력값: {v})")
        for k in ("sido", "sigungu", "industry", "accident_type", "occurred_at", "url", "source_id"):
            if item.get(k) == "":
                item[k] = None
        items.append(item)
    return items

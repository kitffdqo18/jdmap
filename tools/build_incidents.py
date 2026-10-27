"""사고 데이터 파일(docs/data/incidents.js) 갱신 — GitHub Actions 가 하루 3회 실행.

  python -m tools.build_incidents            # 사이렌 수집(설정돼 있으면) + 수동 등록 + 수정 반영
  python -m tools.build_incidents --demo     # 화면 확인용 예시 데이터로 채우기

입력
  data/siren_config.json       사이렌 수집 설정 (enabled 가 true 일 때만 수집)
  data/manual_incidents.csv    직접 등록할 사고 (양식 그대로 행 추가)
  data/corrections.csv         지역 등 고칠 사고 / 숨길 사고 (고유번호 기준)
출력
  docs/data/incidents.js       사이트가 읽는 데이터
  data/unmapped.csv            지역(시도)을 못 찾은 사고 목록 → corrections.csv 로 고치면 됨
"""
import argparse
import csv
import io
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from collector import region  # noqa: E402
from collector.normalize import FIELDS, to_incident  # noqa: E402
from collector.sources import csv_import, kosha_siren  # noqa: E402

KST = timezone(timedelta(hours=9))
OUT = os.path.join(ROOT, "docs", "data", "incidents.js")
PREFIX = "window.JDMAP_DATA = "
CORR_COLS = {"고유번호": "sid", "숨김": "hidden", "시도": "sido", "시군구": "sigungu", "업종": "industry",
             "재해유형": "accident_type", "사망": "deaths", "부상": "injuries", "사고개요": "summary"}


def today():
    return datetime.now(KST).date()


def read_existing(path=OUT):
    if not os.path.exists(path):
        return {}
    txt = open(path, encoding="utf-8").read().strip()
    if txt.startswith(PREFIX):
        txt = txt[len(PREFIX):]
    txt = txt.rstrip(";\n ")
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        return {}
    return {it["sid"]: it for it in data.get("items", []) if it.get("sid")}


def make_item(source, raw_item):
    sid, row, _ = to_incident(raw_item)
    item = {k: row[k] for k in FIELDS}
    item["sid"] = f"{source}-{sid}"[:48]
    item["source"] = source
    return item


def read_csv_file(path):
    if not os.path.exists(path):
        return ""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: 인코딩을 읽지 못했습니다. 엑셀에서 'CSV UTF-8'로 저장해 주세요.")


def load_corrections(path):
    text = read_csv_file(path)
    if not text.strip():
        return {}
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        r = {CORR_COLS[k]: (v or "").strip() for k, v in row.items() if k in CORR_COLS}
        if r.get("sid"):
            out[r["sid"]] = r
    return out


def apply_correction(item, c):
    if c.get("hidden", "").upper() in ("Y", "O", "1", "숨김", "TRUE"):
        return None
    for k in ("sido", "sigungu", "industry", "accident_type", "summary"):
        if c.get(k):
            item[k] = c[k]
    if item.get("sido") and item["sido"] not in region.SIDO_LIST:
        item["sido"], _ = region.extract_region(item["sido"])
    for k in ("deaths", "injuries"):
        if c.get(k, "") != "":
            try:
                item[k] = int(float(c[k]))
            except ValueError:
                pass
    return item


def build(siren_items=None, manual_csv="", corrections=None, existing=None, keep_days=90, now=None):
    """순수 함수: 테스트하기 쉽게 입출력만 다룸."""
    now = now or today()
    items = dict(existing or {})
    # 수동 등록분은 매번 CSV 기준으로 다시 만든다 (CSV 에서 지운 행은 사라짐)
    items = {k: v for k, v in items.items() if v.get("source") != "csv"}
    for raw in siren_items or []:
        it = make_item("siren", raw)
        items[it["sid"]] = it
    if manual_csv.strip():
        for raw in csv_import.parse(manual_csv):
            it = make_item("csv", raw)
            items[it["sid"]] = it
    cutoff = (now - timedelta(days=keep_days - 1)).isoformat()
    out = []
    for sid, it in items.items():
        if (it.get("posted_date") or "") < cutoff:
            continue
        c = (corrections or {}).get(sid)
        it = dict(it)
        if c:
            it = apply_correction(it, c)
            if it is None:
                continue
        out.append(it)
    out.sort(key=lambda x: (x.get("posted_date") or "", x.get("occurred_at") or "", x["sid"]), reverse=True)
    for i, it in enumerate(out, start=1):
        it["id"] = i
    base = max((x["posted_date"] for x in out), default=None)
    return {"base_date": base, "updated_at": datetime.now(KST).isoformat(timespec="minutes"), "items": out}


def write_js(data, path=OUT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(PREFIX)
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")


def write_unmapped(data, path):
    rows = [x for x in data["items"] if not x.get("sido")]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["고유번호", "숨김", "시도", "시군구", "업종", "재해유형", "사망", "부상", "사고개요"])
        for x in rows:
            w.writerow([x["sid"], "", "", x.get("sigungu") or "", x.get("industry") or "", x.get("accident_type") or "",
                        x.get("deaths", 0), x.get("injuries", 0), (x.get("summary") or x.get("title") or "")[:200]])
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--keep-days", type=int, default=int(os.environ.get("KEEP_DAYS", "90")))
    a = ap.parse_args(argv)
    data_dir = os.path.join(ROOT, "data")

    siren = []
    if a.demo:
        from collector_demo import demo_items  # noqa
        siren = demo_items()
    else:
        cfg_path = os.path.join(data_dir, "siren_config.json")
        cfg = kosha_siren.load_config(cfg_path) if os.path.exists(cfg_path) else {}
        if cfg.get("enabled"):
            siren = kosha_siren.fetch(cfg)
            print(f"사이렌 수집: {len(siren)}건")
        else:
            print("사이렌 수집 건너뜀: data/siren_config.json 의 enabled 가 false")

    data = build(siren_items=siren,
                 manual_csv=read_csv_file(os.path.join(data_dir, "manual_incidents.csv")),
                 corrections=load_corrections(os.path.join(data_dir, "corrections.csv")),
                 existing={} if a.demo else read_existing(),
                 keep_days=a.keep_days)
    write_js(data)
    n = write_unmapped(data, os.path.join(data_dir, "unmapped.csv"))
    print(f"저장: docs/data/incidents.js · 사고 {len(data['items'])}건 · 지역 미분류 {n}건 (data/unmapped.csv)")


if __name__ == "__main__":
    main()

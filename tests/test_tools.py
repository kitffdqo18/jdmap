"""python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from tools import build_incidents as bi  # noqa: E402
from tools import geo_finalize, geo_prepare  # noqa: E402
from collector import region  # noqa: E402

TODAY = date(2026, 10, 13)
HEAD = "게시일,발생일시,시도,시군구,업종,재해유형,사망,부상,제목,사고개요,원문링크,고유번호\n"


class TestBuildIncidents(unittest.TestCase):
    def test_manual_csv_and_extract(self):
        csv_text = HEAD + "2026-10-13,,,,,,,,,충청남도 당진시 소재 건설현장에서 근로자 1명이 떨어져 사망,,\n"
        d = bi.build(manual_csv=csv_text, now=TODAY)
        it = d["items"][0]
        self.assertEqual((it["sido"], it["sigungu"], it["industry"], it["accident_type"], it["deaths"]), ("충남", "당진시", "건설업", "떨어짐", 1))
        self.assertTrue(it["sid"].startswith("csv-"))
        self.assertEqual(d["base_date"], "2026-10-13")

    def test_csv_row_removed_disappears_but_siren_kept(self):
        csv_text = HEAD + "2026-10-12,,경기,화성시,제조업,끼임,1,0,,프레스 끼임,,m1\n"
        siren = [{"source_id": "77", "title": "경기 평택시 끼임", "body": "1명 사망", "posted_date": "2026-10-11"}]
        d1 = bi.build(siren_items=siren, manual_csv=csv_text, now=TODAY)
        self.assertEqual(len(d1["items"]), 2)
        existing = {x["sid"]: x for x in d1["items"]}
        d2 = bi.build(siren_items=[], manual_csv=HEAD, existing=existing, now=TODAY)  # 다음 날: 사이렌 목록에서 밀려남, CSV 행 삭제
        self.assertEqual([x["sid"] for x in d2["items"]], ["siren-77"])

    def test_corrections_and_hide(self):
        siren = [{"source_id": "1", "title": "고성군 소재 현장", "body": "추락 1명 사망", "posted_date": "2026-10-13"},
                 {"source_id": "2", "title": "중복 게시", "body": "경기 화성시 끼임", "posted_date": "2026-10-13"}]
        d0 = bi.build(siren_items=siren, now=TODAY)
        self.assertIsNone(next(x for x in d0["items"] if x["sid"] == "siren-1")["sido"])
        corr = {"siren-1": {"sid": "siren-1", "sido": "강원", "sigungu": "고성군"}, "siren-2": {"sid": "siren-2", "hidden": "Y"}}
        d = bi.build(siren_items=siren, corrections=corr, now=TODAY)
        self.assertEqual([(x["sid"], x["sido"], x["sigungu"]) for x in d["items"]], [("siren-1", "강원", "고성군")])

    def test_keep_days(self):
        siren = [{"source_id": "old", "title": "경기 화성시", "body": "", "posted_date": "2026-06-01"},
                 {"source_id": "new", "title": "경기 화성시", "body": "", "posted_date": "2026-10-10"}]
        d = bi.build(siren_items=siren, keep_days=90, now=TODAY)
        self.assertEqual([x["sid"] for x in d["items"]], ["siren-new"])

    def test_js_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "incidents.js")
            d = bi.build(siren_items=[{"source_id": "9", "title": "부산 사하구", "body": "", "posted_date": "2026-10-13"}], now=TODAY)
            bi.write_js(d, p)
            back = bi.read_existing(p)
            self.assertIn("siren-9", back)
            self.assertTrue(open(p, encoding="utf-8").read().startswith("window.JDMAP_DATA = "))

    def test_unmapped_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = bi.build(siren_items=[{"source_id": "x", "title": "소재지 미상 사고", "body": "", "posted_date": "2026-10-13"}], now=TODAY)
            p = os.path.join(tmp, "u.csv")
            self.assertEqual(bi.write_unmapped(d, p), 1)
            corr = bi.load_corrections(p)  # 그대로 corrections.csv 로 쓸 수 있는 형식
            self.assertIn("siren-x", corr)


class TestGeo(unittest.TestCase):
    sq = staticmethod(lambda x: {"type": "Polygon", "coordinates": [[[x, 37], [x + .1, 37], [x + .1, 37.1], [x, 37]]]})

    def test_keys_admdong_fields(self):
        self.assertEqual(geo_prepare.keys_of({"sidonm": "경기도", "sggnm": "수원시장안구"}), ("경기", "수원시"))
        self.assertEqual(geo_prepare.keys_of({"sidonm": "경기도", "sggnm": "수원시장안구"}, keep_gu=True), ("경기", "수원시장안구"))
        self.assertEqual(geo_prepare.keys_of({"sidonm": "서울특별시", "sggnm": "강남구"}), ("서울", "강남구"))
        self.assertEqual(geo_prepare.keys_of({"adm_nm": "경기도 수원시 장안구 파장동"}), ("경기", "수원시"))
        self.assertEqual(geo_prepare.keys_of({"adm_nm": "강원특별자치도 춘천시 신북읍"}), ("강원", "춘천시"))
        self.assertEqual(geo_prepare.keys_of({"adm_nm": "세종특별자치시 조치원읍"}), ("세종", "세종시"))
        self.assertEqual(geo_prepare.keys_of({"SIG_CD": "52111", "SIG_KOR_NM": "전주시 완산구"}), ("전북", "전주시"))
        self.assertEqual(geo_prepare.keys_of({"foo": 1}), (None, None))

    def test_prepare_and_finalize(self):
        gj = {"features": [{"properties": {"sidonm": "경기도", "sggnm": "화성시"}, "geometry": self.sq(126.8)},
                           {"properties": {"adm_nm": "충청남도 당진시 송악읍"}, "geometry": self.sq(126.6)},
                           {"properties": {}, "geometry": self.sq(1)}]}
        fc, skipped = geo_prepare.prepare(gj)
        self.assertEqual(skipped, 1)
        self.assertEqual([f["properties"]["KEY"] for f in fc["features"]], ["경기|화성시", "충남|당진시"])
        sido_fc = {"features": [{"properties": {"SD": "경기"}, "geometry": self.sq(126.123456)}]}
        sido, sgg = geo_finalize.finalize(sido_fc, fc, "출처")
        self.assertEqual(sido["features"][0]["properties"]["name"], "경기도")
        self.assertEqual(sido["features"][0]["geometry"]["coordinates"][0][0][0], 126.1235)
        self.assertEqual([(f["properties"]["sido"], f["properties"]["name"]) for f in sgg["features"]], [("경기", "화성시"), ("충남", "당진시")])


class TestExtract(unittest.TestCase):
    def test_region(self):
        self.assertEqual(region.extract_region("경기도 화성시 소재 공장에서"), ("경기", "화성시"))
        self.assertEqual(region.extract_region("당진시 소재 건설현장"), ("충남", "당진시"))
        self.assertEqual(region.extract_region("경기도 수원시 장안구 소재 공장"), ("경기", "수원시 장안구"))


if __name__ == "__main__":
    unittest.main()

"""사이렌 포스터 글자 읽기 결과 다듬기 시험 (실제 읽기 결과에서 가져온 문장)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from collector import ocr  # noqa: E402
from collector.normalize import to_incident  # noqa: E402
from collector.sources.kosha_siren import _title_date  # noqa: E402


def parse(text):
    _, row, _ = to_incident({"title": "", "body": ocr._clean(text), "posted_date": "2026-10-30"})
    return row


class OcrCleanTest(unittest.TestCase):
    def test_month_and_day_typos(self):
        r = parse("'26년 10훨 24임토) 12:14경 경남 창원시 소새 전사부품 세소 공상 2층에서 부품에 맞아 사망")
        self.assertEqual(r["occurred_at"], "2026-10-24 12:14")
        self.assertEqual((r["sido"], r["sigungu"]), ("경남", "창원시"))

    def test_town_typos(self):
        self.assertEqual(parse("2026년 10월 4일 10:54경 중북 중수시 소새 공장에서 사망")["sigungu"], "충주시")
        self.assertEqual(parse("2026년 10월 15일 13:40경 충북 음선군 소재 공장에서 사망")["sigungu"], "음성군")
        self.assertEqual(parse("2026년 10월 28일 10:10경 경기 고양 소새 현장에서 사망")["sigungu"], "고양시")

    def test_merged_gwangju(self):
        self.assertEqual(parse("2026년 10월 9일 09:05경 전남광수 남구 소재 아파트 현장에서 사망")["sido"], "광주")
        self.assertEqual(parse("2026년 10월 9일 09:05경 전남광주 여수시 소재 공장에서 사망")["sido"], "전남")

    def test_sejong(self):
        self.assertEqual(parse("2026년 10월 27일 16:53경 세종 장군면 소재 도로 현장에서 사망")["sigungu"], "세종시")

    def test_title_date(self):
        self.assertEqual(_title_date("(261028)중대재해 발생 알림(1)"), "2026-10-28")
        self.assertEqual(_title_date("중대재해 발생 알림"), "")

    def test_pick(self):
        self.assertEqual(ocr._pick("ㅣ . 무너5", ocr.TYPES), "무너짐")
        self.assertEqual(ocr._pick("기타업", ocr.INDUSTRIES), "기타")


if __name__ == "__main__":
    unittest.main()

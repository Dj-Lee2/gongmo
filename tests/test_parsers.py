"""파서·정규화·병합 테스트. 저장한 픽스처로 돌린다."""
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from collector.sources import wevity, contestkorea, thinkgood, hermes
from collector import normalize as N
from collector import merge as M
from collector.fields import map_fields, map_targets, looks_like_activity, is_non_contest
from collector.common import today_kst

FIX = Path(__file__).parent / "fixtures"


class TestWevity(unittest.TestCase):
    def setUp(self):
        self.items = wevity.parse((FIX / "wevity_list.html").read_text(encoding="utf-8"))

    def test_count_and_fields(self):
        self.assertGreaterEqual(len(self.items), 10)
        it = self.items[0]
        self.assertIn("화성특례시 AI CF", it["title"])
        self.assertEqual(it["organizer"], "화성특례시")
        self.assertTrue(it["source_url"].startswith("https://www.wevity.com"))

    def test_no_header_row(self):
        self.assertTrue(all("공모전명" != i["title"] for i in self.items))

    def test_dday_to_enddate(self):
        it = self.items[0]  # D-10
        self.assertEqual(it["end_date"], (today_kst() + timedelta(days=10)).isoformat())


class TestContestKorea(unittest.TestCase):
    def setUp(self):
        self.items = contestkorea.parse((FIX / "contestkorea_list.html").read_text(encoding="utf-8"))

    def test_rich_fields(self):
        self.assertGreaterEqual(len(self.items), 20)
        it = self.items[0]
        self.assertIn("지식재산 아이디어", it["title"])
        self.assertIn("한국산림복지진흥원", it["organizer"])
        self.assertTrue(it["target_raw"])
        self.assertEqual(it["end_date"], "2026-10-31")
        self.assertEqual(it["status_raw"], "접수중")


class TestThinkGood(unittest.TestCase):
    def setUp(self):
        self.items = thinkgood.parse((FIX / "thinkcontest_list.json").read_text(encoding="utf-8"))

    def test_json_fields(self):
        self.assertGreaterEqual(len(self.items), 5)
        it = self.items[0]
        self.assertTrue(it["title"])
        self.assertTrue(it["end_date"])
        self.assertTrue(it["poster_url"].startswith("https://"))

    def test_official_url_scheme(self):
        # 공식 링크는 https만 남긴다
        for it in self.items:
            if it["official_url"] is not None:
                self.assertTrue(it["official_url"].startswith("https://"))


class TestHermes(unittest.TestCase):
    def setUp(self):
        data = json.loads((FIX / "hermes_sample.json").read_text(encoding="utf-8"))
        self.items = hermes.parse(data)

    def test_verified_and_block(self):
        self.assertTrue(self.items)
        it = self.items[0]
        self.assertTrue(it["verified"])
        self.assertIn("status", it["hermes"])
        self.assertIn("label", it["hermes"])


class TestFields(unittest.TestCase):
    def test_map_fields(self):
        self.assertIn("IT·AI·데이터", map_fields("웹/모바일/IT, AI"))
        self.assertIn("영상·사진·UCC", map_fields("영상/UCC/사진"))
        self.assertEqual(map_fields(""), ["기타"])

    def test_targets(self):
        self.assertIn("누구나", map_targets("대한민국 국민 누구나"))
        self.assertIn("대학생", map_targets("대학생, 대학원생"))

    def test_activity_filter(self):
        self.assertTrue(looks_like_activity("대외활동/서포터즈"))
        self.assertFalse(looks_like_activity("기획/아이디어"))

    def test_non_contest(self):
        self.assertTrue(is_non_contest("홈페이지 만족도 설문조사"))
        self.assertTrue(is_non_contest("대학생 서포터즈 모집"))
        self.assertTrue(is_non_contest("가을맞이 경품 이벤트"))
        self.assertFalse(is_non_contest("2026 아이디어 공모전"))
        self.assertFalse(is_non_contest("AI 해커톤"))


class TestNormalize(unittest.TestCase):
    def test_prize(self):
        self.assertEqual(N.parse_prize("상금 1000만원"), 10000000)
        self.assertEqual(N.parse_prize("대상 1억원"), 100000000)
        self.assertIsNone(N.parse_prize("상장 수여"))

    def test_status_and_dday(self):
        t = today_kst()
        future = (t + timedelta(days=5)).isoformat()
        past = (t - timedelta(days=5)).isoformat()
        self.assertEqual(N.compute_status(None, future, ""), "접수중")
        self.assertEqual(N.compute_status(None, past, ""), "마감")
        self.assertEqual(N.compute_status((t + timedelta(days=2)).isoformat(), future, ""), "접수예정")
        self.assertEqual(N.compute_dday(future), 5)

    def test_norm_title(self):
        a = N.norm_title("제6회 2026 별별화성 공모전 (AI부문)")
        b = N.norm_title("별별화성")
        self.assertEqual(a, b)


class TestMerge(unittest.TestCase):
    def _mk(self, title, org, end, source, url, verified=False, hermes_block=None):
        raw = {"source": source, "source_url": url, "title": title, "organizer": org,
               "fields_raw": "아이디어", "target_raw": "누구나", "prize_text": "100만원",
               "end_date": end, "start_date": None, "status_raw": "접수중",
               "verified": verified, "hermes": hermes_block}
        return N.normalize(raw)

    def test_merge_same(self):
        t = (today_kst() + timedelta(days=10)).isoformat()
        a = self._mk("2026 별별화성 공모전", "화성특례시", t, "위비티", "https://a")
        b = self._mk("별별화성 공모전", "화성특례시청", t, "헤르메스", "https://b", verified=True,
                     hermes_block={"status": "recommended", "highlight": True})
        merged = M.merge_all([a, b])
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["verified"])
        self.assertEqual(len(merged[0]["sources"]), 2)

    def test_no_merge_different_deadline(self):
        t1 = (today_kst() + timedelta(days=10)).isoformat()
        t2 = (today_kst() + timedelta(days=40)).isoformat()
        a = self._mk("무슨 공모전", "서울시", t1, "위비티", "https://a")
        b = self._mk("무슨 공모전", "서울시", t2, "씽굿", "https://b")
        self.assertEqual(len(M.merge_all([a, b])), 2)

    def test_no_merge_different_org(self):
        t = (today_kst() + timedelta(days=10)).isoformat()
        a = self._mk("사진 공모전", "부산시", t, "위비티", "https://a")
        b = self._mk("사진 공모전", "국립생태원", t, "씽굿", "https://b")
        self.assertEqual(len(M.merge_all([a, b])), 2)


if __name__ == "__main__":
    unittest.main()

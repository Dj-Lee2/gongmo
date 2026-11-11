"""개인 맥락 빼기·같은 id 합치기·띄어쓰기 검증 테스트."""
import unittest

from collector.merge import dedupe_by_id, merge_all
from collector.normalize import normalize
from collector.privacy import needs_spacing, same_letters, scrub_item, scrub_text


class TestScrub(unittest.TestCase):
    def test_removes_personal_clauses(self):
        s = ("데이터 분석·활용 관심 국민 누구나 개인 또는 최대5인팀. 통합운영규정 제5조2항 주최·주관·참여·후원기관 소속 제외; "
             "예시청/예시 연구원은 열거된 기관 목록에 없으나 소속기관 참여·상금·IP 내부확인 필요.")
        out = scrub_text(s)
        self.assertNotIn("예시청", out)
        self.assertNotIn("소속기관", out)
        self.assertIn("주최·주관·참여·후원기관 소속 제외", out)

    def test_honorific_orfa_and_user(self):
        self.assertEqual(scrub_text("공고일기준 재학생;예시님현재재학상태미확인"), "공고일기준 재학생")
        self.assertEqual(scrub_text("A 금지 · 수상작의 논문·예시서비스 전용 금지 가능성 · B 필수"), "A 금지 · B 필수")
        self.assertEqual(scrub_text("일반인 만19~34세 제한; 사용자 연령과 불일치"), "일반인 만19~34세 제한")
        self.assertEqual(scrub_text("지역 자격증빙 필수. 알려진 부산 거주/재직과 맞지 않아 추천 제외"), "지역 자격증빙 필수.")

    def test_keeps_public_rules(self):
        for s in ("아이디어·사용자경험, 사업성·지속가능성", "결과는 개별 통지한다", "한국환경보전원 소속 임직원 제외",
                  "총 상금 4.16억원. 대상 1팀", "https://example.kr/a.b?c=1 참조"):
            self.assertEqual(scrub_text(s), s)

    def test_hard_words_warn(self):
        from collector.privacy import leftover_warnings
        self.assertEqual(len(leftover_warnings([{"id": "a", "title": "예시서비스 공모전", "organizer": ""},
                                                {"id": "b", "title": "보통 공모전", "organizer": ""}])), 1)

    def test_idempotent_and_no_dangling(self):
        s = "11/21현장발표필수;소속기관참가·상금·업무IP확인필요. · 신청폼로그인후분량·동의미확인;실제경험만활용."
        once = scrub_text(s)
        self.assertEqual(scrub_text(once), once)
        self.assertNotIn("; ·", once)
        self.assertNotIn("소속기관", once)

    def test_item_fields(self):
        it = {"title": "예시청 주최 공모전", "target_raw": "누구나; 예시님 직종에 부합", "prize_text": "",
              "hermes": {"reason": "예시님의통계·RAG보다암호전문성비중높음.", "idea": "x"}}
        scrub_item(it)
        self.assertEqual(it["title"], "예시청 주최 공모전")  # 요강 자체는 안 건드림
        self.assertEqual(it["target_raw"], "누구나")
        self.assertEqual(it["hermes"]["reason"], "")


class TestDedupe(unittest.TestCase):
    def _raw(self, src, org, hermes=None):
        return {"source": src, "source_url": "https://e.kr/" + src, "title": "2026 AI 플랫폼 구축 경진대회",
                "organizer": org, "fields_raw": "IT", "end_date": "2099-10-25", "start_date": "2026-10-01",
                "hermes": hermes, "verified": bool(hermes)}

    def test_same_title_deadline_different_org_merges(self):
        items = [normalize(self._raw("씽굿", "데이커")), normalize(self._raw("헤르메스", "DAKER", {"label": "추천"}))]
        out = merge_all(items)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["sources"]), 2)
        self.assertTrue(out[0]["hermes"])

    def test_dedupe_by_id_prefers_hermes(self):
        a = normalize(self._raw("씽굿", "가"))
        b = normalize(self._raw("헤르메스", "나", {"label": "추천"}))
        for x in (a, b):
            x.pop("norm_title", None)
        out = dedupe_by_id([a, b])
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["hermes"])
        self.assertEqual({s["name"] for s in out[0]["sources"]}, {"씽굿", "헤르메스"})


    def test_generic_title_different_org_gets_distinct_ids(self):
        mk = lambda org, src: normalize({"source": src, "source_url": "https://e.kr/" + src, "title": "사진 공모전",
                                         "organizer": org, "fields_raw": "사진", "end_date": "2099-01-01"})
        out = merge_all([mk("부산시", "위비티"), mk("국립생태원", "씽굿")])
        self.assertEqual(len(out), 2)
        self.assertNotEqual(out[0]["id"], out[1]["id"])


class TestEntities(unittest.TestCase):
    def test_clean_text(self):
        from collector.normalize import clean_text
        self.assertEqual(clean_text("뮤지컬 &lt;프라테르니테&gt; &amp; 알&amp;닭 &quot;춤&quot;"), '뮤지컬 <프라테르니테> & 알&닭 "춤"')
        self.assertEqual(clean_text("&amp;lt;x&amp;gt;"), "<x>")
        self.assertEqual(clean_text("그대로 A&B"), "그대로 A&B")

    def test_normalize_unescapes_title(self):
        it = normalize({"source": "콘테스트코리아", "source_url": "https://e.kr", "title": "연극 &lt;이별&gt; 공모전",
                        "organizer": "극단 &amp; 친구", "fields_raw": "문학", "end_date": "2099-01-01"})
        self.assertEqual(it["title"], "연극 <이별> 공모전")
        self.assertEqual(it["organizer"], "극단 & 친구")


class TestVersionedIndex(unittest.TestCase):
    def test_assets_get_content_hash(self):
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location("pv", pathlib.Path(__file__).resolve().parent.parent / "deploy" / "publish_vps.py")
        pv = importlib.util.module_from_spec(spec); spec.loader.exec_module(pv)
        site = pathlib.Path(__file__).resolve().parent.parent / "site"
        html = pv.versioned_index(site).decode("utf-8")
        self.assertRegex(html, r'href="/style\.css\?v=[0-9a-f]{10}"')
        self.assertRegex(html, r'src="/app\.js\?v=[0-9a-f]{10}"')
        self.assertNotIn('src="/app.js"', html)


class TestHermesFix(unittest.TestCase):
    def _pv(self):
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location("pv2", pathlib.Path(__file__).resolve().parent.parent / "deploy" / "publish_vps.py")
        pv = importlib.util.module_from_spec(spec); spec.loader.exec_module(pv); return pv

    def test_label_and_closed_without_date(self):
        pv = self._pv()
        a = {"status": "접수중", "end_date": None, "hermes": {"status": "excluded_non_competitive", "label": "excluded_non_competitive"}}
        b = {"status": "접수중", "end_date": None, "hermes": {"status": "registration_closed", "label": "접수마감"}}
        c = {"status": "접수중", "end_date": "2099-01-01", "hermes": {"status": "closed", "label": "마감"}}
        a["sources"] = [{"name": "씽굿"}]
        d = {"status": "접수중", "end_date": None, "sources": [{"name": "헤르메스"}], "hermes": {"status": "excluded_non_competitive", "label": "x"}}
        out = pv.fix_hermes([a, b, c, d])
        self.assertEqual(len(out), 3)  # 헤르메스만 있고 경연 아님 → 뺀다
        self.assertEqual(a["hermes"]["label"], "경연 아님")
        self.assertEqual(b["status"], "마감")
        self.assertEqual(c["status"], "접수중")  # 날짜가 있으면 날짜가 이긴다

    def test_collector_closed_status(self):
        from collector.sources import hermes
        raw = hermes.parse({"competitions": [{"name": "X 해커톤", "status": "closed", "facts": {}}]})
        self.assertEqual(normalize(raw[0])["status"], "마감")


class TestSpacing(unittest.TestCase):
    def test_detect(self):
        self.assertTrue(needs_spacing("5개품목의계절성·기상·시장반입량을결합한설명가능한가격예측과농가출하시점참고화면"))
        self.assertFalse(needs_spacing("5개 품목의 계절성·기상·시장 반입량을 결합한 설명 가능한 가격 예측"))
        self.assertFalse(needs_spacing("짧은글"))

    def test_same_letters(self):
        self.assertTrue(same_letters("가나다라", "가나 다라"))
        self.assertFalse(same_letters("가나다라", "가나 다마"))


if __name__ == "__main__":
    unittest.main()

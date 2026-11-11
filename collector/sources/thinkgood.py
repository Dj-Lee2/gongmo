"""씽굿(thinkcontest) 공모전 목록 수집.

화면은 템플릿이고 실제 목록은 JS가 POST로 부르는 JSON 엔드포인트가 준다:
  POST /thinkgood/user/contest/subList.do  (application/json)
응답 res.listJsonData 각 항목에 제목·주최·접수기간·마감일·D-day·분야·대상·상금·공식링크·포스터가 들어 있다.
"""
import json

from ..common import fetch

NAME = "씽굿"
BASE = "https://www.thinkcontest.com"
ENDPOINT = BASE + "/thinkgood/user/contest/subList.do"
DISPLAY = BASE + "/thinkgood/common/display.do"


def _prize(it):
    p = (it.get("prize_money") or "").strip()
    if p and p not in ("기타", "미정", "0"):
        return p
    aw = (it.get("award_size_nm") or "").strip()
    return aw if aw and aw != "기타" else ""


def parse(text):
    """subList.do JSON 본문 → raw 항목 리스트."""
    items = []
    try:
        data = json.loads(text)
    except ValueError:
        return items
    for it in (data.get("listJsonData") or []):
        pk = it.get("contest_pk")
        title = (it.get("program_nm") or "").strip()
        if not pk or not title:
            continue
        poster_url = None
        if it.get("poster_path") and it.get("poster_name"):
            poster_url = "%s?filepath=%s&filename=%s" % (DISPLAY, it["poster_path"], it["poster_name"])
        hp = (it.get("hompage_url") or "").strip()
        official = hp if hp.startswith("https://") else None
        items.append({
            "source": NAME,
            "source_url": "%s/thinkgood/user/contest/view.do?contest_pk=%s" % (BASE, pk),
            "title": title,
            "organizer": (it.get("host_company") or "").strip(),
            "fields_raw": (it.get("contest_field_nm") or "").strip(),
            "target_raw": (it.get("enter_qualified_nm") or "").strip(),
            "prize_text": _prize(it),
            "start_date": it.get("accept_dt"),
            "end_date": it.get("finish_dt"),
            "dday_raw": (it.get("dday") or "").strip(),
            "status_raw": (it.get("process_nm") or "").strip(),
            "is_new": False,
            "poster_url": poster_url,
            "official_url": official,
        })
    return items


def collect(max_pages=20):
    """최신순으로 넘기며 접수중/접수예정 위주로 모은다. 마감만 연속으로 나오면 멈춘다."""
    all_items, pages_ok = [], 0
    note = ""
    closed_streak = 0
    for page in range(1, max_pages + 1):
        body = json.dumps({"recordsPerPage": 10, "currentPageNo": page, "searchStatus": "Y",
                           "sidx": "", "sord": ""})
        status, text = fetch(ENDPOINT, data=body,
                             headers={"Content-Type": "application/json",
                                      "X-Requested-With": "XMLHttpRequest"})
        if status != 200 or not text:
            note = "페이지 %d 응답 %s" % (page, status)
            break
        got = parse(text)
        if not got:
            break
        all_items.extend(got)
        pages_ok += 1
        # 이 페이지가 전부 마감이면 streak, 2페이지 연속 전부 마감이면 중단
        if got and all(g["status_raw"] == "마감" for g in got):
            closed_streak += 1
            if closed_streak >= 2:
                break
        else:
            closed_streak = 0
    ok = pages_ok > 0
    return all_items, ok, note or ("%d개 페이지" % pages_ok)

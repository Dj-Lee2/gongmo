"""헤르메스(운영자의 AI 비서) 검증 장부 읽기(읽기 전용, 선택 출처).

장부 JSON의 competitions를 항목으로 바꾸고, 맞춤 판단(상태·이유·아이디어·요강 사실)을 함께 담는다.
장부가 없으면 이 출처는 0건으로 지나간다.
"""
import os
from pathlib import Path

from ..common import read_json

NAME = "헤르메스"
# VPS에서는 GONGMO_HERMES_LEDGER로 다른 경로(수집 기계가 보낸 자료에서 되살린 장부)를 준다
LEDGER = Path(os.environ.get("GONGMO_HERMES_LEDGER") or os.path.expanduser("~/.hermes/cron/state/ai-competition-watch.json"))

# 장부 status → 화면 맞춤 라벨
HSTATUS = {
    "recommended": "추천",
    "conditional": "조건부",
    "watchlist": "관심",
    "not_selected": "제외",
    "closed": "마감",
    "registration_closed": "접수마감",
    "deadline_unverified": "확인필요",
    "excluded_non_competitive": "경연 아님",
}
# 마감일이 없을 때 이 상태면 '마감'으로 본다(날짜가 있으면 날짜가 이긴다)
CLOSED = {"closed", "registration_closed"}
# 맞춤 섹션에 올리는 상태
HIGHLIGHT = {"recommended", "conditional", "watchlist"}


def _first(facts, *keys):
    for k in keys:
        v = facts.get(k)
        if v:
            return v
    return ""


def _to_text(v):
    if isinstance(v, list):
        return " · ".join(str(x) for x in v)
    return str(v) if v else ""


def parse(data):
    """장부 dict → raw 항목 리스트."""
    items = []
    for c in (data.get("competitions") or []):
        facts = c.get("facts") or {}
        name = (c.get("name") or "").strip()
        if not name:
            continue
        official = (c.get("official_url") or "").strip()
        reason = _to_text(_first(facts, "reason", "fit_judgment", "fit", "reason_not_selected"))
        idea = _to_text(_first(facts, "idea_proposal"))
        hs = c.get("status") or ""
        hblock = {
            "status": hs,
            "label": HSTATUS.get(hs, hs),
            "highlight": hs in HIGHLIGHT,
            "reason": reason,
            "idea": idea,
            "eligibility": _to_text(_first(facts, "eligibility")),
            "submission": _to_text(_first(facts, "submission", "submission_method")),
            "ip": _to_text(_first(facts, "ip", "IP")),
            "ai": _to_text(_first(facts, "ai", "AI", "ai_data_rules")),
            "restrictions": _to_text(_first(facts, "restrictions", "limitations")),
            "fee": _to_text(_first(facts, "fee", "application_fee")),
            "burden": _to_text(_first(facts, "burden_estimate")),
            "last_checked": c.get("last_checked") or "",
        }
        items.append({
            "source": NAME,
            "source_url": official or None,
            "title": name,
            "organizer": _to_text(_first(facts, "organizer")),
            "fields_raw": _to_text(_first(facts, "track", "name")) or name,
            "target_raw": _to_text(_first(facts, "eligibility")),
            "prize_text": _to_text(_first(facts, "prize")),
            "start_date": _first(facts, "open_date", "open_at") or None,
            "end_date": c.get("deadline") or None,
            "end_time": _first(facts, "deadline_time") or None,
            "dday_raw": "",
            "status_raw": "마감" if hs in CLOSED else "",
            "is_new": False,
            "poster_url": None,
            "official_url": official if official.startswith("https://") else None,
            "verified": True,
            "hermes": hblock,
        })
    return items


def collect():
    data = read_json(LEDGER)
    if not data:
        return [], False, "장부 없음"
    items = parse(data)
    return items, bool(items), "%d건, 갱신 %s" % (len(items), data.get("updated_at", "?"))

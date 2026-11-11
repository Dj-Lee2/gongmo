"""raw 항목 → 표준 항목. 분야·대상 매핑, 상태·D-day 계산(Asia/Seoul), 상금 파싱, 제목 정규화."""
import hashlib
import html
import re

from .common import parse_iso_date, today_kst
from .fields import map_fields, map_targets, looks_like_activity, is_non_contest

# 제목 정규화: 괄호·연도·회차·흔한 꼬리말 제거
_RE_BRACKET = re.compile(r"[\(\[【<][^\)\]】>]*[\)\]】>]")
_RE_ROUND = re.compile(r"제?\s*\d+\s*(회|차|기|th|nd|st|rd)", re.I)
_RE_YEAR = re.compile(r"20\d\d\s*(년도|년)?")
_RE_TAIL = re.compile(r"(공모전|공모|대회|경진대회|경진|콘테스트|챌린지|해커톤|페스티벌|공모\s*사업|아이디어\s*공모)")
_RE_NONWORD = re.compile(r"[^0-9a-z가-힣]")


def clean_text(s):
    """HTML 엔티티(&lt; &amp; &quot; …)를 글자로 푼다. 두 번 감싼 것(&amp;lt;)까지. 화면은 따로 이스케이프한다."""
    if not s or not isinstance(s, str):
        return s
    for _ in range(2):
        t = html.unescape(s)
        if t == s:
            break
        s = t
    return s


def norm_title(title):
    t = (title or "").lower()
    t = _RE_BRACKET.sub(" ", t)
    t = _RE_ROUND.sub(" ", t)
    t = _RE_YEAR.sub(" ", t)
    t = _RE_TAIL.sub(" ", t)
    t = _RE_NONWORD.sub("", t)
    return t


def make_id(title, end_date):
    key = norm_title(title) + "|" + (end_date or "")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def parse_prize(text):
    """상금 문구에서 대표(최대) 금액을 원 단위로. 자신 없으면 None."""
    if not text:
        return None
    best = 0
    for m in re.finditer(r"(\d[\d,\.]*)\s*억", text):
        best = max(best, int(float(m.group(1).replace(",", "")) * 100000000))
    for m in re.finditer(r"(\d[\d,]*)\s*만\s*원", text):
        best = max(best, int(m.group(1).replace(",", "")) * 10000)
    if best == 0:
        for m in re.finditer(r"(\d{4,})\s*원", text):
            best = max(best, int(m.group(1)))
    if best == 0:
        # 단위 없는 순수 숫자(예: "10000000"). 1만원 이상일 때만 원 단위로 본다.
        bare = text.replace(",", "").strip()
        if bare.isdigit() and int(bare) >= 10000:
            best = int(bare)
    return best or None


def compute_status(start_date, end_date, status_raw):
    today = today_kst()
    ed = parse_iso_date(end_date)
    sd = parse_iso_date(start_date)
    if ed:
        if today > ed:
            return "마감"
        if sd and today < sd:
            return "접수예정"
        return "접수중"
    # 날짜 없음: 원문 상태로
    if "예정" in (status_raw or ""):
        return "접수예정"
    if "마감" in (status_raw or "") and "임박" not in (status_raw or ""):
        return "마감"
    return "접수중"


def compute_dday(end_date):
    ed = parse_iso_date(end_date)
    if not ed:
        return None
    return (ed - today_kst()).days


def normalize(raw):
    """raw 항목 하나 → 표준 항목(공모전 아닌 것이면 None)."""
    title = clean_text((raw.get("title") or "").strip())
    if not title:
        return None
    fields_raw = raw.get("fields_raw") or ""
    if looks_like_activity(fields_raw):
        return None
    # 헤르메스 항목은 사람이 검증한 것이라 제목 필터를 적용하지 않는다
    if raw.get("source") != "헤르메스" and is_non_contest(title):
        return None
    end_date = None
    ed = parse_iso_date(raw.get("end_date"))
    if ed:
        end_date = ed.isoformat()
    start_date = None
    sd = parse_iso_date(raw.get("start_date"))
    if sd:
        start_date = sd.isoformat()
    status = compute_status(start_date, end_date, raw.get("status_raw"))
    item = {
        "id": make_id(title, end_date),
        "title": title,
        "norm_title": norm_title(title),
        "organizer": clean_text((raw.get("organizer") or "").strip()),
        "fields": map_fields(fields_raw) if raw.get("source") != "헤르메스" else map_fields(title + " " + fields_raw),
        "target_raw": clean_text((raw.get("target_raw") or "").strip()),
        "target_tags": map_targets(raw.get("target_raw") or raw.get("fields_raw") or ""),
        "prize_text": clean_text((raw.get("prize_text") or "").strip()),
        "prize_total_won": parse_prize(raw.get("prize_text")),
        "start_date": start_date,
        "end_date": end_date,
        "end_time": raw.get("end_time"),
        "status": status,
        "dday": compute_dday(end_date),
        "is_new": bool(raw.get("is_new")),
        "sources": [{"name": raw.get("source"), "url": raw.get("source_url")}] if raw.get("source_url") else [{"name": raw.get("source"), "url": None}],
        "official_url": raw.get("official_url"),
        "poster_url": raw.get("poster_url"),
        "verified": bool(raw.get("verified")),
        "hermes": raw.get("hermes"),
    }
    return item


def normalize_all(raw_items):
    out = []
    for r in raw_items:
        n = normalize(r)
        if n:
            out.append(n)
    return out

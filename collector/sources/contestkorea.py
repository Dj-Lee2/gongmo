"""콘테스트코리아 대회·공모전 목록 수집.

목록은 list.php에 RetrieveFlag=Y를 줘야 서버가 항목을 그려 준다(int_gbn=1 = 대회·공모전).
항목에서 제목·분야·주최·대상·접수기간·D-day·상태를 뽑는다.
"""
import re
from datetime import timedelta

from ..common import fetch, today_kst

NAME = "콘테스트코리아"
BASE = "https://www.contestkorea.com"


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _year_for(mm, dd, today):
    """MM.DD에 연도를 붙인다. 올해 기준으로 가장 가까운(과거 60일~미래 400일) 연도."""
    for y in (today.year, today.year + 1, today.year - 1):
        try:
            from datetime import date
            d = date(y, mm, dd)
        except ValueError:
            continue
        if today - timedelta(days=60) <= d <= today + timedelta(days=400):
            return d
    return None


def parse(html):
    items = []
    m = re.search(r'<div class="list_style_2">\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
    if not m:
        return items
    today = today_kst()
    # 카드마다 <div class="title">로 시작한다(내부 <ul class="host"><li> 중첩 때문에 li로 못 쪼갠다)
    cards = re.split(r'<div class="title">', m.group(1))
    for li in cards[1:]:
        a = re.search(r'<a href="(view\.php[^"]*)">(.*?)</a>', li, re.S)
        if not a:
            continue
        href, inner = a.group(1), a.group(2)
        cats = re.findall(r'<span class="category">(.*?)</span>', inner, re.S)
        fields_raw = ", ".join(_clean(c) for c in cats)
        txt = re.search(r'<span class="txt">(.*?)</span>', inner, re.S)
        title = _clean(txt.group(1)) if txt else _clean(re.sub(r'<span class="category">.*?</span>', "", inner, flags=re.S))
        if not title:
            continue
        host = re.search(r'<li class="icon_1">(.*?)</li>', li, re.S)
        organizer = _clean(re.sub(r"<strong>.*?</strong>", "", host.group(1), flags=re.S)).lstrip(". ") if host else ""
        tgt = re.search(r'<li class="icon_2">(.*?)</li>', li, re.S)
        target_raw = _clean(re.sub(r"<strong>.*?</strong>", "", tgt.group(1), flags=re.S)).lstrip(". ") if tgt else ""
        # 접수 기간: step-1 "10.14~10.31"
        step1 = re.search(r'<span class="step-1">.*?</em>(.*?)</span>', li, re.S)
        start_date = end_date = None
        if step1:
            per = _clean(step1.group(1))
            mm = re.findall(r"(\d{1,2})\.(\d{1,2})", per)
            if len(mm) >= 2:
                sd = _year_for(int(mm[0][0]), int(mm[0][1]), today)
                ed = _year_for(int(mm[1][0]), int(mm[1][1]), today)
                start_date = sd.isoformat() if sd else None
                end_date = ed.isoformat() if ed else None
        day = re.search(r'<span class="day">D-(\d+)</span>', li)
        if not end_date and day:
            end_date = (today + timedelta(days=int(day.group(1)))).isoformat()
        cond = re.search(r'<span class="condition">(.*?)</span>', li, re.S)
        status_raw = _clean(cond.group(1)) if cond else ""
        items.append({
            "source": NAME,
            "source_url": "%s/sub/%s" % (BASE, href),
            "title": title,
            "organizer": organizer,
            "fields_raw": fields_raw,
            "target_raw": target_raw,
            "prize_text": "",
            "start_date": start_date,
            "end_date": end_date,
            "dday_raw": "D-%s" % day.group(1) if day else "",
            "status_raw": status_raw,
            "is_new": "ic_new.gif" in li,
            "poster_url": None,
            "official_url": None,
        })
    return items


def collect(max_pages=5):
    all_items, pages_ok = [], 0
    note = ""
    for page in range(1, max_pages + 1):
        url = "%s/sub/list.php?int_gbn=1&RetrieveFlag=Y&displayrow=40&page=%d" % (BASE, page)
        status, html = fetch(url)
        if status != 200 or not html:
            note = "페이지 %d 응답 %s" % (page, status)
            break
        got = parse(html)
        if not got:
            break
        all_items.extend(got)
        pages_ok += 1
    ok = pages_ok > 0
    return all_items, ok, note or ("%d개 페이지" % pages_ok)

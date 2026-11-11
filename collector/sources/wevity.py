"""위비티 공모전 목록 수집. 목록 페이지에서 제목·주최·분야·D-day·상태를 뽑는다.

상세 페이지는 서버에서 내용을 주지 않아(JS 렌더) 목록 정보만 쓴다.
마감일은 D-day로 계산한다(수집 시점 기준, Asia/Seoul).
"""
import re
from datetime import timedelta

from ..common import fetch, today_kst

NAME = "위비티"
BASE = "https://www.wevity.com"
LIST_URL = BASE + "/?c=find&s=1&gub=1"


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def parse(html):
    """목록 HTML → raw 항목 리스트."""
    items = []
    m = re.search(r'<ul class="list">(.*?)</ul>', html, re.S)
    if not m:
        return items
    today = today_kst()
    for li in re.findall(r"<li.*?</li>", m.group(1), re.S):
        if 'class="top"' in li:
            continue
        a = re.search(r'<div class="tit">\s*<a href="([^"]*)">(.*?)</a>', li, re.S)
        if not a:
            continue
        href, title_html = a.group(1), a.group(2)
        ix = re.search(r"ix=(\d+)", href)
        if not ix:
            continue
        # 제목에서 배지(신규/SPECIAL) 제거
        title = _clean(re.sub(r"<span[^>]*>.*?</span>", "", title_html, flags=re.S))
        is_new = "stat new" in title_html
        sub = re.search(r'<div class="sub-tit">(.*?)</div>', li, re.S)
        fields_raw = ""
        if sub:
            fields_raw = _clean(sub.group(1)).replace("분야 :", "").strip()
        organ = re.search(r'<div class="organ">(.*?)</div>', li, re.S)
        organizer = _clean(organ.group(1)) if organ else ""
        day = re.search(r'<div class="day">(.*?)</div>', li, re.S)
        day_txt = _clean(day.group(1)) if day else ""
        dday = re.search(r"D-(\d+)", day_txt)
        end_date = None
        if dday:
            end_date = (today + timedelta(days=int(dday.group(1)))).isoformat()
        status_raw = "접수중"
        if "마감임박" in day_txt:
            status_raw = "접수중"
        elif "접수예정" in day_txt or "D-day" in day_txt and "예정" in day_txt:
            status_raw = "접수예정"
        items.append({
            "source": NAME,
            "source_url": "%s/?c=find&s=1&gub=1&gbn=view&ix=%s" % (BASE, ix.group(1)),
            "title": title,
            "organizer": organizer,
            "fields_raw": fields_raw,
            "target_raw": "",
            "prize_text": "",
            "start_date": None,
            "end_date": end_date,
            "dday_raw": day_txt,
            "status_raw": status_raw,
            "is_new": is_new,
            "poster_url": None,
            "official_url": None,
        })
    return items


def collect(max_pages=4):
    """여러 페이지를 받아 합친다. (항목들, 성공여부, 메모)."""
    all_items, pages_ok = [], 0
    note = ""
    for gp in range(1, max_pages + 1):
        status, html = fetch("%s&gp=%d" % (LIST_URL, gp))
        if status != 200 or not html:
            note = "페이지 %d 응답 %s" % (gp, status)
            break
        got = parse(html)
        if not got:
            break
        all_items.extend(got)
        pages_ok += 1
    ok = pages_ok > 0
    return all_items, ok, note or ("%d개 페이지" % pages_ok)

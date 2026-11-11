"""빌드: data/raw를 정규화·병합해 site/data/*.json을 만든다.

- 최초 발견일(first_seen)을 data/seen.json에 기록해 '오늘 새로'를 계산한다.
- 마감 30일 지난 항목은 버린다.
- 날짜·D-day·건수는 코드로 계산(Asia/Seoul).
- 지난번 빌드와 같은 공모전이면 id를 그대로 이어 쓴다(관심·진행 기록이 id에 묶여 있음).
- 출처 목록 앞쪽 몇 쪽만 모으므로, 아직 마감 전인데 이번 목록에서 밀려난 공모전은 마지막으로 본 날부터
  CARRY_DAYS일 동안 지난번 내용으로 남긴다(목록에서 사라졌다고 마감은 아니다).
"""
import sys
from datetime import timedelta

from .common import RAW, SITE_DATA, DATA, read_json, write_json, now_kst, today_kst
from .fields import FIELDS
from .normalize import normalize_all
from .merge import merge_all
from .privacy import scrub_item, leftover_warnings
from .sources import wevity, contestkorea, thinkgood, hermes

SOURCE_NAMES = [wevity.NAME, contestkorea.NAME, thinkgood.NAME, hermes.NAME]
SEEN_PATH = DATA / "seen.json"
KEEP_CLOSED_DAYS = 30
CARRY_DAYS = 14


def _title_key(it):
    from .normalize import norm_title, clean_text
    return (norm_title(clean_text(it.get("title") or "")), it.get("end_date") or "")


def _keep_ids(items, prev):
    """새 항목 id를 지난번 같은 공모전의 id로 맞춘다: 출처 주소가 겹치거나, 정규화 제목+마감일이 같으면."""
    by_url, by_title = {}, {}
    for p in prev:
        for s in p.get("sources") or []:
            if s.get("url"):
                by_url.setdefault(s["url"], p["id"])
        by_title.setdefault(_title_key(p), p["id"])
    used = set()
    cands_of = {}
    for it in items:
        cands = []
        for s in it.get("sources") or []:
            c = by_url.get(s.get("url"))
            if c and c not in cands:
                cands.append(c)
        tc = by_title.get(_title_key(it))
        if tc and tc not in cands:
            cands.append(tc)
        cands_of[id(it)] = cands
        old = None
        for s in it.get("sources") or []:
            cand = by_url.get(s.get("url"))
            if cand and cand not in used:
                old = cand
                break
        if not old:
            cand = by_title.get(_title_key(it))
            if cand and cand not in used:
                old = cand
        if old:
            it["id"] = old
            used.add(old)
    # 같은 id가 둘이 되는 일은 없게(이어 쓴 id와 새로 만든 id가 우연히 같을 때)
    seen = set()
    for it in items:
        if it["id"] in seen:
            it["id"] = it["id"][:15] + "x"
        seen.add(it["id"])
    # 지난번 두 줄이 이번에 한 줄로 합쳐졌으면, 사라진 쪽 id를 aliases로 남긴다(화면이 관심·진행 기록을 옮겨 줌).
    # 한동안 사이트에 안 들어온 브라우저도 옮겨지도록 지난번 aliases를 계속 이어 간다.
    prev_alias = {p["id"]: p.get("aliases") or [] for p in prev}
    for it in items:
        al = [c for c in cands_of.get(id(it), []) if c != it["id"] and c not in seen]
        al += [c for c in prev_alias.get(it["id"], []) if c not in al and c not in seen]
        if al:
            it["aliases"] = al
        else:
            it.pop("aliases", None)
    return items


def _carry_over(items, prev, last):
    """이번 목록에 없지만 마감 전이고 최근 CARRY_DAYS일 안에 본 공모전을 지난번 내용으로 남긴다."""
    from .normalize import compute_status, compute_dday
    from .merge import similar_competition
    from .normalize import norm_title
    have = {it["id"] for it in items}
    have |= {a for it in items for a in it.get("aliases") or []}  # 한 줄로 합쳐져 사라진 id는 되살리지 않는다
    now_keys = [{"end_date": it.get("end_date"), "norm_title": norm_title(it.get("title")),
                 "organizer": it.get("organizer"), "sources": it.get("sources")} for it in items]
    now_urls = {}
    for i, it in enumerate(items):
        for s in it.get("sources") or []:
            if s.get("url"):
                now_urls.setdefault(s["url"], i)
    cutoff = (today_kst() - timedelta(days=CARRY_DAYS)).isoformat()
    n = 0
    for p in prev:
        if p.get("id") in have or (last.get(p.get("id")) or "") < cutoff:
            continue
        pk = {"end_date": p.get("end_date"), "norm_title": norm_title(p.get("title")),
              "organizer": p.get("organizer"), "sources": []}
        hit = next((now_urls[s["url"]] for s in p.get("sources") or [] if s.get("url") in now_urls), None)
        if hit is None:
            hit = next((i for i, k in enumerate(now_keys) if similar_competition(pk, k)), None)
        twin = items[hit] if hit is not None else None
        if twin is not None:  # 이번 목록에 제목만 조금 다르게 다시 나온 같은 공모전
            twin.setdefault("aliases", [])
            if p["id"] not in twin["aliases"]:
                twin["aliases"].append(p["id"])
            have.add(p["id"])
            continue
        q = dict(p)
        if q.get("end_date"):
            q["status"] = compute_status(q.get("start_date"), q.get("end_date"), q.get("status"))
            q["dday"] = compute_dday(q.get("end_date"))
        if q.get("status") == "마감":
            continue
        q["carried"] = True
        q.pop("triage", None); q.pop("link", None)
        items.append(q)
        have.add(q["id"])
        n += 1
    return items, n


def _load_all_raw():
    raw = []
    for name in SOURCE_NAMES:
        d = read_json(RAW / ("%s.json" % name), {"items": []})
        raw.extend(d.get("items", []))
    return raw


def _apply_first_seen(items, store=None):
    store = store if store is not None else read_json(SEEN_PATH, None)
    today = today_kst().isoformat()
    if store is None:
        store = {"_baseline": today, "ids": {}}
    baseline = store.get("_baseline", today)
    ids = store.setdefault("ids", {})
    last = store.setdefault("last", {})
    for it in items:
        if not it.get("carried"):
            last[it["id"]] = today
        fs = ids.get(it["id"])
        if not fs:
            fs = today
            ids[it["id"]] = fs
        it["first_seen"] = fs
        # 기준선을 세운 첫날 항목은 '신규'로 세지 않는다(그날 통째로 들어온 것이라).
        it["is_new_today"] = (fs == today) and (today != baseline) and it["status"] != "마감"
    write_json(SEEN_PATH, store)
    return items


def _drop_old_closed(items):
    cutoff = today_kst() - timedelta(days=KEEP_CLOSED_DAYS)
    out = []
    for it in items:
        if it["status"] == "마감" and it.get("dday") is not None and it["dday"] < -KEEP_CLOSED_DAYS:
            continue
        if it["status"] == "마감" and it.get("end_date"):
            from .common import parse_iso_date
            ed = parse_iso_date(it["end_date"])
            if ed and ed < cutoff:
                continue
        out.append(it)
    return out


def _sort_key(it):
    # 접수중/예정 먼저, 그 안에서 마감 임박 순
    rank = {"접수중": 0, "접수예정": 1, "마감": 2}.get(it["status"], 3)
    dday = it.get("dday")
    dday = dday if dday is not None else 9999
    return (rank, dday)


def compute_stats(merged):
    open_items = [x for x in merged if x["status"] == "접수중"]
    return {
        "total": len(merged),
        "open": len(open_items),
        "closing7": len([x for x in open_items if x.get("dday") is not None and 0 <= x["dday"] <= 7]),
        "new_today": len([x for x in merged if x.get("is_new_today")]),
        "upcoming": len([x for x in merged if x["status"] == "접수예정"]),
        "closed": len([x for x in merged if x["status"] == "마감"]),
        "verified": len([x for x in merged if x.get("verified") and x["status"] != "마감"]),
        "recommended": len([x for x in merged if (x.get("hermes") or {}).get("highlight")]),
    }


def build():
    raw = _load_all_raw()
    items = normalize_all(raw)
    merged = merge_all(items)
    prev = read_json(SITE_DATA / "items.json", []) or []
    store = read_json(SEEN_PATH, None)
    merged = _keep_ids(merged, prev)
    for it in merged:
        it.pop("carried", None)
    merged, carried = _carry_over(merged, prev, (store or {}).get("last", {}))
    if carried:
        print("목록에서 밀려났지만 마감 전이라 남긴 공모전: %d건" % carried)
    merged = _apply_first_seen(merged, store)
    merged = _drop_old_closed(merged)
    merged.sort(key=_sort_key)
    # 사이트가 공개라서 헤르메스 메모의 개인 맥락(호칭·소속·운영 서비스)은 내보내기 전에 뺀다.
    for it in merged:
        scrub_item(it)
    for w in leftover_warnings(merged):
        print("!!! 민감 낱말 남음(제목·주최):", w)

    today = today_kst()
    stats = compute_stats(merged)
    collect_status = read_json(RAW / "collect_status.json", {"sources": {}})
    meta = {
        "generated_at": now_kst().isoformat(),
        "generated_date": today.isoformat(),
        "fields": FIELDS,
        "stats": stats,
        "sources": collect_status.get("sources", {}),
    }
    write_json(SITE_DATA / "items.json", merged)
    write_json(SITE_DATA / "meta.json", meta)
    print("빌드 완료: 총 %d건 (접수중 %d, 7일내마감 %d, 오늘신규 %d, 예정 %d, 검증 %d, 추천 %d)" % (
        stats["total"], stats["open"], stats["closing7"], stats["new_today"],
        stats["upcoming"], stats["verified"], stats["recommended"]))
    return meta


if __name__ == "__main__":
    build()
    sys.exit(0)

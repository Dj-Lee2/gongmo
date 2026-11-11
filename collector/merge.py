"""여러 출처의 표준 항목을 병합한다.

같은 공모전 판정: 제목 정규화 일치 + 마감일 일치(한쪽이 비면 통과) + 주최 유사.
헤르메스 항목이 섞이면 verified=true와 맞춤 정보를 붙인다.
"""
import re

_SRC_RANK = {"헤르메스": 0, "씽굿": 1, "콘테스트코리아": 2, "위비티": 3}


def _norm_org(s):
    s = re.sub(r"(주최|주관|후원|·|\s)", "", s or "")
    return s.lower()


def org_similar(a, b):
    a, b = _norm_org(a), _norm_org(b)
    if not a or not b:
        return True
    if a in b or b in a:
        return True
    ta, tb = set(re.findall(r"[가-힣a-z0-9]{2,}", a)), set(re.findall(r"[가-힣a-z0-9]{2,}", b))
    return bool(ta & tb)


def same_competition(x, y):
    if x["norm_title"] != y["norm_title"]:
        return False
    if not x["norm_title"]:
        return False
    ex, ey = x.get("end_date"), y.get("end_date")
    if ex and ey and ex != ey:
        return False
    # 제목·마감일이 같고 제목이 흔한 말(예: '사진')이 아니면 같은 공모전으로 본다.
    # 출처마다 주최 표기가 달라('(사)'·'사단법인', 주최·주관 기관 중 하나만 적기) 갈라지던 문제.
    if ex and ey and len(x["norm_title"]) >= 5:
        return True
    return org_similar(x.get("organizer", ""), y.get("organizer", ""))


def _pick(a, b):
    return a if a else b


def merge_pair(base, other):
    """other를 base에 합친다. base를 수정해 돌려준다."""
    # 출처 합치기(중복 url 제거)
    seen = {(s.get("name"), s.get("url")) for s in base["sources"]}
    for s in other["sources"]:
        if (s.get("name"), s.get("url")) not in seen:
            base["sources"].append(s)
            seen.add((s.get("name"), s.get("url")))
    base["organizer"] = _pick(base.get("organizer"), other.get("organizer"))
    base["target_raw"] = _pick(base.get("target_raw"), other.get("target_raw"))
    base["prize_text"] = _pick(base.get("prize_text"), other.get("prize_text"))
    base["official_url"] = _pick(base.get("official_url"), other.get("official_url"))
    base["poster_url"] = _pick(base.get("poster_url"), other.get("poster_url"))
    base["start_date"] = _pick(base.get("start_date"), other.get("start_date"))
    base["end_date"] = _pick(base.get("end_date"), other.get("end_date"))
    base["end_time"] = _pick(base.get("end_time"), other.get("end_time"))
    base["is_new"] = base.get("is_new") or other.get("is_new")
    # 분야·대상 합집합
    for f in other.get("fields", []):
        if f != "기타" and f not in base["fields"]:
            base["fields"].append(f)
    base["fields"] = [f for f in base["fields"] if f != "기타"] or ["기타"]
    for t in other.get("target_tags", []):
        if t not in base["target_tags"]:
            base["target_tags"].append(t)
    # 상금 최대
    pv = [v for v in (base.get("prize_total_won"), other.get("prize_total_won")) if v]
    base["prize_total_won"] = max(pv) if pv else None
    # 검증
    if other.get("verified"):
        base["verified"] = True
    if other.get("hermes"):
        base["hermes"] = base.get("hermes") or other["hermes"]
    return base


def merge_all(items):
    """표준 항목 리스트 → 병합된 리스트. 출처 우선순위대로 base를 고른다."""
    items = sorted(items, key=lambda x: _SRC_RANK.get(x["sources"][0]["name"], 9))
    groups = []
    for it in items:
        hit = None
        for g in groups:
            if same_competition(g, it):
                hit = g
                break
        if hit:
            merge_pair(hit, it)
        else:
            groups.append(it)
    groups = merge_similar(groups)
    # 상태·D-day는 end_date 기준으로 이미 계산됨. 병합으로 end_date가 채워졌으면 다시 계산.
    from .normalize import compute_status, compute_dday
    for g in groups:
        if g.get("end_date"):
            g["status"] = compute_status(g.get("start_date"), g.get("end_date"), g["status"])
            g["dday"] = compute_dday(g.get("end_date"))
    # 흔한 제목·같은 마감일의 서로 다른 공모전은 id가 겹친다 → 뒤엣것은 주최까지 넣어 새 id.
    import hashlib
    seen = set()
    for g in groups:
        if g["id"] in seen:
            key = "%s|%s|%s" % (g.get("norm_title", ""), g.get("end_date") or "", _norm_org(g.get("organizer")))
            g["id"] = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        seen.add(g["id"])
        g.pop("norm_title", None)
    return dedupe_by_id(groups)


def similar_competition(x, y):
    """정확히 같지는 않지만 같은 공모전인지(출처마다 제목을 조금씩 다르게 적은 경우).

    - 마감일이 둘 다 있고 같아야 한다.
    - 같은 출처에 서로 다른 공고로 따로 올라와 있으면(예: 한 대회의 두 부문) 정규화 제목이 완전히 같을 때만 합친다.
    - 정규화 제목(괄호·연도·회차·'공모전' 같은 꼬리말·기호 제거)이 8자 이상이고
      비슷한 정도 0.85 이상이거나, 한쪽이 다른 쪽에 통째로 들어 있고 차이가 8자 이하이면 같다고 본다.
    - 주최가 같으면 비슷한 정도 0.6 이상이거나 한쪽 제목이 다른 쪽에 들어 있으면 같다고 본다.
    """
    import difflib
    ex, ey = x.get("end_date"), y.get("end_date")
    if not ex or ex != ey:
        return False
    a, b = x.get("norm_title") or "", y.get("norm_title") or ""
    if not a or not b:
        return False
    if a == b:  # 흔한 제목('사진 공모전')은 주최가 달라 보이면 따로
        return len(a) >= 5 or org_similar(x.get("organizer"), y.get("organizer"))
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    ox, oy = _norm_org(x.get("organizer")), _norm_org(y.get("organizer"))
    same_org = bool(ox and oy and (ox in oy or oy in ox))
    contained = short in long_
    # 같은 출처에 서로 다른 공고로 따로 올라와 있으면(한 대회의 여러 부문·과정) 따로 둔다.
    # 다만 주최가 같고 한쪽 제목이 다른 쪽에 통째로 들어 있으면 다시 올린 같은 공고로 본다.
    sx = {}
    for s in x.get("sources") or []:
        sx.setdefault(s.get("name"), set()).add(s.get("url"))
    for s in y.get("sources") or []:
        urls = sx.get(s.get("name"))
        if urls and s.get("url") not in urls and not (same_org and contained and len(short) >= 5):
            return False
    # 주최가 같으면 기준을 낮춘다: 주최명·부제가 제목 앞뒤에 붙는 경우
    if same_org and ((contained and len(short) >= 3) or (ratio >= 0.6 and len(short) >= 5)):
        return True
    if len(short) < 8:
        return False
    if contained and len(long_) - len(short) <= 8:
        return True
    return ratio >= 0.85


def merge_similar(groups):
    """similar_competition인 것끼리 합친다. 헤르메스가 섞인 쪽, 그다음 출처가 많은 쪽을 기준으로."""
    by_date = {}
    for g in groups:
        by_date.setdefault(g.get("end_date") or "", []).append(g)
    dropped = set()
    for date_, lst in by_date.items():
        if not date_ or len(lst) < 2:
            continue
        lst.sort(key=lambda g: (0 if g.get("hermes") else 1, -len(g.get("sources") or [])))
        for i, base in enumerate(lst):
            if id(base) in dropped:
                continue
            for other in lst[i + 1:]:
                if id(other) in dropped:
                    continue
                if similar_competition(base, other):
                    merge_pair(base, other)
                    base.setdefault("_merged_titles", []).append(other.get("title"))
                    dropped.add(id(other))
    out = [g for g in groups if id(g) not in dropped]
    for g in out:
        g.pop("_merged_titles", None)
    return out


def dedupe_by_id(items):
    """같은 id가 둘 이상이면 하나로 합친다(화면에서 카드가 두 번 나오고 상세가 엇갈리는 것 방지).

    헤르메스가 섞인 쪽을 기준으로 삼고, 상태·D-day는 날짜로 다시 계산한다. 순서는 처음 나온 자리를 지킨다.
    """
    from .normalize import compute_status, compute_dday
    by_id, order = {}, []
    for it in items:
        k = it.get("id")
        if k not in by_id:
            by_id[k] = it
            order.append(k)
            continue
        base, other = by_id[k], it
        if other.get("hermes") and not base.get("hermes"):
            base, other = other, base
        merge_pair(base, other)
        if base.get("end_date"):
            base["status"] = compute_status(base.get("start_date"), base.get("end_date"), base.get("status"))
            base["dday"] = compute_dday(base.get("end_date"))
        base["is_new_today"] = bool(base.get("is_new_today") and other.get("is_new_today"))
        if other.get("first_seen") and (not base.get("first_seen") or other["first_seen"] < base["first_seen"]):
            base["first_seen"] = other["first_seen"]
        by_id[k] = base
    return [by_id[k] for k in order]

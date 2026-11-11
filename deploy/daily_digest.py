#!/usr/bin/env python3
"""공모모아 아침 알림(텔레그램, Hermes cron no_agent): 새 맞춤 공고 · 곧 마감 · 갱신 이상.

- 새 맞춤 공고: 오늘 처음 본(first_seen=오늘) 공모전 중 헤르메스 맞춤(highlight) 또는 1차 추천·검토.
- 곧 마감: 3일 안에 마감하는 헤르메스 맞춤·1차 추천·검토.
- 이상: 오늘 전체 갱신(full)이 안 돌았거나 단계가 실패, 출처 수집 실패·급감(직전 유지), 원문 안 열림이 많음.
출력이 곧 알림 글이다(빈 출력이면 알림 없음 — 이 스크립트는 늘 한 통을 낸다).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
# 운영 폴더 OPS_ROOT: repo/(이 저장소) · state/ · public/ · site/data/(받은 자료). GONGMO_ROOT로 바꿀 수 있다.
OPS_ROOT = Path(os.environ.get("GONGMO_ROOT") or Path(__file__).resolve().parent.parent.parent)
PUBLIC = OPS_ROOT / "public" / "data"
STATE = OPS_ROOT / "state"
REPO = OPS_ROOT / "repo"
SITE = "https://gongmo.orfa.shop/"
WEEK = "월화수목금토일"


def _j(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def tag(it):
    h, t = it.get("hermes") or {}, it.get("triage") or {}
    if it.get("_mine"):
        return "관심"
    if h.get("highlight"):
        return "헤르메스 " + (h.get("label") or "맞춤")
    if t.get("grade") in ("추천", "검토"):
        return "1차 %s %s" % (t["grade"], t.get("score", ""))
    return ""


def rank(it):
    h, t = it.get("hermes") or {}, it.get("triage") or {}
    order = {"추천": 0, "조건부": 1, "관심": 2}
    if h.get("highlight"):
        return (0, order.get(h.get("label"), 3), it.get("dday") or 999)
    return (1, -(t.get("score") or 0), it.get("dday") or 999)


NUMS = {}  # 알림 번호 → 공모전 id(답장 "3번 별로"를 feedback.py --num 3으로 받으려고 digest_last.json에 남김)


def line(it, today):
    ed = it.get("end_date")
    when = ""
    if ed:
        d = (date.fromisoformat(ed) - today).days
        when = " — 마감 %d.%d(%s)" % (int(ed[5:7]), int(ed[8:10]), "오늘" if d == 0 else "D-%d" % d)
    n = len(NUMS) + 1
    NUMS[n] = it["id"]
    link = SITE + ("c/" + it["code"] if it.get("code") else "#id=" + it["id"])
    return "%d. [%s] %s%s\n  %s" % (n, tag(it), it.get("title", "")[:60], when, link)


def main():
    now = datetime.now(KST)
    today = now.date()
    items = _j(STATE / "items-full.json", []) or _j(PUBLIC / "items.json", [])  # 운영자용 전체 자료(헤르메스·1차 판단 포함)
    out = ["🧩 공모모아 %d/%d(%s) 아침" % (today.month, today.day, WEEK[today.weekday()])]
    warn = []
    if not items:
        warn.append("⚠ 공개 자료를 읽지 못했습니다(public/data/items.json).")
    picked = [it for it in items if it.get("status") != "마감" and tag(it)]
    new = sorted([it for it in picked if it.get("first_seen") == today.isoformat()], key=rank)
    soon = sorted([it for it in picked if it.get("dday") is not None and 0 <= it["dday"] <= 3 and it not in new],
                  key=lambda x: (x.get("dday"), rank(x)))
    if new:
        out.append("\n새로 들어온 맞춤 공고 %d건" % len(new))
        out += [line(it, today) for it in new[:6]]
        if len(new) > 6:
            out.append("  …외 %d건" % (len(new) - 6))
    else:
        out.append("\n새로 들어온 맞춤 공고는 없습니다.")
    if soon:
        out.append("\n3일 안에 마감하는 맞춤 공고 %d건" % len(soon))
        out += [line(it, today) for it in soon[:6]]
        if len(soon) > 6:
            out.append("  …외 %d건" % (len(soon) - 6))

    # ── 갱신 상태 ──
    last = _j(STATE / "last_full.json", {})
    at = last.get("at", "")
    try:
        ran_today = datetime.fromisoformat(at).astimezone(KST).date() == today
    except ValueError:
        ran_today = False
    if not ran_today:
        warn.append("⚠ 오늘 아침 전체 갱신이 돌지 않았습니다(마지막 %s)." % (at[:16].replace("T", " ") or "기록 없음"))
    else:
        bad = [name for key, name in (("collect", "수집"), ("build", "빌드"), ("link", "원문 확인"),
                                      ("triage", "1차 판단"), ("publish", "게시")) if last.get(key) not in ("0", "-")]
        if bad:
            warn.append("⚠ 오늘 갱신 중 실패한 단계: %s" % ", ".join(bad))
    # 띄어쓰기 교정·1차 판단은 claude CLI를 쓴다 — 로그인이 풀리면 조용히 멈추므로 직접 확인
    try:
        import subprocess
        pr = subprocess.run([str(Path.home() / ".local/bin/claude"), "-p", "ok라고만 답해", "--model", "haiku"],
                            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        if "authenticate" in (pr.stdout + pr.stderr).lower() or pr.returncode != 0:
            warn.append("⚠ claude CLI 로그인이 풀려 1차 판단·띄어쓰기 교정이 멈췄습니다(VPS에서 claude 다시 로그인 필요).")
    except Exception:
        pass
    cs = _j(REPO / "data" / "raw" / "collect_status.json", {}).get("sources", {})
    for name, s in cs.items():
        if name == "헤르메스":
            continue
        if not s.get("ok"):
            warn.append("⚠ %s 수집 실패 — 직전 자료 유지 (%s)" % (name, (s.get("note") or "")[:60]))
        elif s.get("kept_previous"):
            warn.append("⚠ %s 공고 수 급감 — 직전 자료 유지 (%s)" % (name, (s.get("note") or "")[:60]))
    links = _j(STATE / "links.json", {})
    if links:
        badn = sum(1 for v in links.values() if not v.get("ok"))
        if badn > max(20, len(links) * 0.1):
            warn.append("⚠ 원문이 안 열리는 공모전이 %d건으로 많습니다." % badn)
    hnote = (cs.get("헤르메스") or {}).get("note", "")
    if "갱신 " in hnote:
        try:
            hd = datetime.fromisoformat(hnote.split("갱신 ")[-1]).astimezone(KST).date()
            if (today - hd).days >= 2:
                warn.append("⚠ 헤르메스 검증이 %d일째 새로 오지 않습니다(수집 기계 확인)." % (today - hd).days)
        except ValueError:
            pass
    open_n = sum(1 for it in items if it.get("status") == "접수중")
    out.append("\n" + ("\n".join(warn) if warn else "✅ 갱신 정상") + " · 접수중 %d건" % open_n)
    out.append(SITE)
    if NUMS:
        out.append("\n↩ 이 알림에 답장으로 \"2번 좋아\", \"5번 별로, 영상 대회는 빼\"처럼 말씀하시면 1차 판단에 반영합니다.")
        try:
            p = STATE / "digest_last.json"
            p.write_text(json.dumps({"date": today.isoformat(), "nums": NUMS}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

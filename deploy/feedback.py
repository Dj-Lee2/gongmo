#!/usr/bin/env python3
"""운영자 반응(아침 알림 답장 등)을 1차 판단에 반영한다.

  feedback.py add --id <공모전 id> --verdict 좋음|별로 [--note "이유"]
  feedback.py add --num 3 --verdict 별로 --note "영상 대회"   # 오늘 아침 알림의 3번
  feedback.py list
  feedback.py remove --id <id>

- 기록은 state/feedback.json(저장소 밖, 비공개). triage가 프로필 뒤에 '최근 반응' 예시로 붙여 넘기고,
  반응이 바뀌면 프로필 해시가 바뀌어 다음 갱신에 전부 다시 판단한다.
- '영상 대회는 빼' 같은 일반 규칙은 state/profile.md의 '## 선호·부담'에 직접 적는다(이 스크립트는 공모전 하나하나 반응만).
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# 운영 폴더 OPS_ROOT: repo/(이 저장소) · state/ · public/ · site/data/(받은 자료). GONGMO_ROOT로 바꿀 수 있다.
OPS_ROOT = Path(os.environ.get("GONGMO_ROOT") or Path(__file__).resolve().parent.parent.parent)
STATE = OPS_ROOT / "state"
PUBLIC = STATE / "items-full.json"  # 운영자용 전체 자료
VERDICTS = {"좋음": "좋음", "like": "좋음", "good": "좋음", "별로": "별로", "dislike": "별로", "bad": "별로"}
KEEP = 40  # 프롬프트에 넣는 최근 반응 수


def load(state):
    try:
        return json.loads((state / "feedback.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(state, fb):
    p = state / "feedback.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(fb, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(p)


def prompt_block(state):
    """triage가 프로필 뒤에 붙이는 글. 반응이 없으면 빈 글(해시가 안 바뀜)."""
    fb = load(state)
    if not fb:
        return ""
    rows = sorted(fb.values(), key=lambda v: v.get("at", ""), reverse=True)[:KEEP]
    out = ["", "## 지원자가 직접 남긴 반응(최근순) — 비슷한 공모전 판단에 참고"]
    for v in rows:
        out.append("- [%s] %s%s" % (v["verdict"], v.get("title", "")[:80], (" — " + v["note"][:120]) if v.get("note") else ""))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "list", "remove"])
    ap.add_argument("--id", default="")
    ap.add_argument("--num", type=int, default=0, help="오늘 아침 알림의 번호")
    ap.add_argument("--verdict", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--state", default=str(STATE))
    a = ap.parse_args()
    state = Path(a.state)
    fb = load(state)
    if a.cmd == "list":
        for k, v in sorted(fb.items(), key=lambda kv: kv[1].get("at", "")):
            print(k, v["verdict"], v.get("at", "")[:10], v.get("title", "")[:50], "—", v.get("note", ""))
        return 0
    iid = a.id
    if a.num:
        last = json.loads((state / "digest_last.json").read_text(encoding="utf-8"))
        nums = {str(n): i for n, i in last.get("nums", {}).items()}
        if str(a.num) not in nums:
            print("알림 %s에 %d번이 없습니다(1~%d)" % (last.get("date"), a.num, len(nums)), file=sys.stderr)
            return 2
        iid = nums[str(a.num)]
    if not iid:
        print("--id 또는 --num이 필요합니다", file=sys.stderr)
        return 2
    if a.cmd == "remove":
        print("지움" if fb.pop(iid, None) else "없음", iid)
        save(state, fb)
        return 0
    verdict = VERDICTS.get(a.verdict.strip().lower())
    if not verdict:
        print("--verdict는 좋음 또는 별로", file=sys.stderr)
        return 2
    items = {i["id"]: i for i in json.loads(PUBLIC.read_text(encoding="utf-8"))}
    it = items.get(iid)
    if not it:
        print("공모전 %s를 찾지 못했습니다" % iid, file=sys.stderr)
        return 2
    fb[iid] = {"verdict": verdict, "note": a.note.strip(), "title": it.get("title", ""),
               "at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")}
    save(state, fb)
    print("기록:", verdict, it.get("title", "")[:60], ("— " + a.note) if a.note else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())

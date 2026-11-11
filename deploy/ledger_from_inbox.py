#!/usr/bin/env python3
"""수집 기계가 보낸 공모모아 자료(inbox items.json)에서 헤르메스 검증 장부를 되살린다.

헤르메스 검증(맞춤 판단)은 아직 수집 기계에서 만들어지고, VPS는 그 결과를 rsync로 받은 items.json에만 갖고 있다.
VPS가 직접 수집·빌드하려면 collector.sources.hermes가 읽는 장부 모양이 필요하므로,
헤르메스 출처가 섞인 항목의 hermes 칸을 장부 항목으로 되돌린다. 원본 장부가 오면 그것을 쓰면 된다.

  python3 deploy/ledger_from_inbox.py --inbox <OPS_ROOT>/site/data/items.json --out <OPS_ROOT>/state/hermes-ledger.json
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# 운영 폴더 OPS_ROOT: repo/(이 저장소) · state/ · public/ · site/data/(받은 자료). GONGMO_ROOT로 바꿀 수 있다.
OPS_ROOT = Path(os.environ.get("GONGMO_ROOT") or Path(__file__).resolve().parent.parent.parent)

# hermes 칸 → 장부 facts 키(collector.sources.hermes.parse가 읽는 첫 번째 이름)
FACT_KEYS = {
    "reason": "reason", "idea": "idea_proposal", "eligibility": "eligibility", "submission": "submission",
    "ip": "ip", "ai": "ai", "restrictions": "restrictions", "fee": "fee", "burden": "burden_estimate",
}


def to_ledger(items, updated_at=""):
    comps = []
    for it in items:
        hm = it.get("hermes")
        if not isinstance(hm, dict) or not hm.get("status"):
            continue
        hsrc = [s for s in it.get("sources") or [] if s.get("name") == "헤르메스"]
        facts = {fk: hm.get(hk) for hk, fk in FACT_KEYS.items() if hm.get(hk)}
        facts.update({k: v for k, v in (("organizer", it.get("organizer")), ("prize", it.get("prize_text")),
                                        ("open_date", it.get("start_date")), ("deadline_time", it.get("end_time"))) if v})
        comps.append({
            "name": it.get("title") or "",
            "official_url": (hsrc[0].get("url") if hsrc and hsrc[0].get("url") else it.get("official_url")) or "",
            "status": hm.get("status"),
            "deadline": it.get("end_date"),
            "last_checked": hm.get("last_checked") or "",
            "facts": facts,
        })
    return {"updated_at": updated_at, "rebuilt_from": "inbox", "competitions": comps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", default=str(OPS_ROOT / "site" / "data" / "items.json"))
    ap.add_argument("--out", default=str(OPS_ROOT / "state" / "hermes-ledger.json"))
    a = ap.parse_args()
    try:
        items = json.loads(Path(a.inbox).read_text(encoding="utf-8"))
        meta = json.loads((Path(a.inbox).parent / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("inbox를 읽지 못해 장부를 그대로 둠:", e)
        return 0
    note = ((meta.get("sources") or {}).get("헤르메스") or {}).get("note", "")
    upd = note.split("갱신 ")[-1] if "갱신 " in note else meta.get("generated_at", "")
    led = to_ledger(items, upd)
    if not led["competitions"]:
        print("헤르메스 항목이 없어 장부를 그대로 둠")
        return 0
    out = Path(a.out)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False)
    os.replace(tmp, out)
    print("헤르메스 장부 %d건(갱신 %s)" % (len(led["competitions"]), upd))
    return 0


if __name__ == "__main__":
    sys.exit(main())

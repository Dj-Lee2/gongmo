"""수집 오케스트레이터: 출처별 raw를 받아 data/raw/에 저장하고 상태를 남긴다.

- 한 출처가 실패해도 나머지로 진행한다.
- 직전 성공분보다 50% 넘게 줄면 그 출처는 직전 raw를 유지한다(사이트가 비는 오탐 방지).
"""
import sys

from .common import RAW, read_json, write_json, now_kst
from .sources import wevity, contestkorea, thinkgood, hermes

WEB_SOURCES = [wevity, contestkorea, thinkgood]


def _save_raw(name, items):
    write_json(RAW / ("%s.json" % name), {"items": items, "count": len(items)})


def _load_raw(name):
    d = read_json(RAW / ("%s.json" % name), {"items": [], "count": 0})
    return d.get("items", [])


def run(hermes_only=False):
    """hermes_only=True면 웹 출처는 건드리지 않고 헤르메스 장부만 다시 읽는다(VPS: 수집 기계 자료가 바뀌었을 때)."""
    old = read_json(RAW / "collect_status.json", {"sources": {}})
    status = {"collected_at": now_kst().isoformat() if not hermes_only else old.get("collected_at", now_kst().isoformat()),
              "sources": {}}
    for mod in WEB_SOURCES:
        if hermes_only:
            if mod.NAME in old.get("sources", {}):
                status["sources"][mod.NAME] = old["sources"][mod.NAME]
            continue
        name = mod.NAME
        try:
            items, ok, note = mod.collect()
        except Exception as e:  # noqa: BLE001 - 한 출처 오류가 전체를 막지 않게
            items, ok, note = [], False, "오류: %s" % e
        prev = _load_raw(name)
        if ok and items:
            if prev and len(items) < 0.5 * len(prev):
                status["sources"][name] = {"ok": True, "count": len(prev), "kept_previous": True,
                                           "note": "%s → 직전 %d건보다 급감(%d건), 직전 유지" % (note, len(prev), len(items))}
            else:
                _save_raw(name, items)
                status["sources"][name] = {"ok": True, "count": len(items), "note": note}
        else:
            status["sources"][name] = {"ok": False, "count": len(prev), "kept_previous": bool(prev),
                                       "note": note or "수집 실패, 직전 유지"}
    # 헤르메스(읽기 전용, 급감 가드 불필요)
    try:
        hitems, hok, hnote = hermes.collect()
    except Exception as e:  # noqa: BLE001
        hitems, hok, hnote = [], False, "오류: %s" % e
    if hok and hitems:
        _save_raw(hermes.NAME, hitems)
        status["sources"][hermes.NAME] = {"ok": True, "count": len(hitems), "note": hnote}
    else:
        status["sources"][hermes.NAME] = {"ok": False, "count": len(_load_raw(hermes.NAME)),
                                          "kept_previous": True, "note": hnote}
    write_json(RAW / "collect_status.json", status)
    for n, s in status["sources"].items():
        print("  %-8s ok=%s count=%s  %s" % (n, s["ok"], s["count"], s.get("note", "")))
    return status


if __name__ == "__main__":
    run(hermes_only="--hermes-only" in sys.argv)
    sys.exit(0)

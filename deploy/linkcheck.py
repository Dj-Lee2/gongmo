#!/usr/bin/env python3
"""원문이 아직 살아 있는지 확인하고, 1차 판단에 쓸 공고문 글을 모은다(VPS, 하루 두 번).

- 대상: 마감 전 공모전. 공식 공고(official_url)와 출처 상세 페이지를 연다.
- '마감'으로 바꾸는 것은 확실한 증거가 있을 때만: 410 응답, 또는 공고 제목이 보이는 페이지에
  '접수가 마감되었습니다' 같은 문장. 그냥 안 열리는 것(시간 초과·403·404·5xx)은 '원문 확인 안 됨'으로만
  기록하고, 두 번 연속일 때 화면에 보인다. 해외 서버에서 막는 국내 사이트가 있어 안 열림 ≠ 마감.
- 열 때 예절: 호스트마다 1.2초 간격, robots.txt가 막은 주소는 열지 않음, 응답은 800KB까지만.
- 결과: state/links.json { id: {url, code, ok, fails, closed, why, checked} }, state/pages/<id>.txt(공고문 글, 6000자)

  python3 deploy/linkcheck.py --items site/data/items.json --state <OPS_ROOT>/state
"""
import argparse
import html as H
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector.common import now_kst, today_kst  # noqa: E402

# 운영 폴더 OPS_ROOT: repo/(이 저장소) · state/ · public/ · site/data/(받은 자료). GONGMO_ROOT로 바꿀 수 있다.
OPS_ROOT = Path(os.environ.get("GONGMO_ROOT") or Path(__file__).resolve().parent.parent.parent)

UA = "Mozilla/5.0 (compatible; gongmo-linkcheck/1.0; +https://gongmo.orfa.shop)"
TIMEOUT = 10
MAX_BYTES = 800_000
HOST_GAP = 1.2
CLOSED_PHRASES = re.compile(
    r"(접수(가|이)?\s*마감(되었|됐|되었습니다|된)|모집(이)?\s*마감(되었|됐)|마감(된|되었습니다|됨)\s*(공모|대회|행사|이벤트|모집)|"
    r"종료(된|되었습니다)\s*(공모|대회|행사|이벤트|모집)|(공모|대회|모집|이벤트|행사)(이|가|는)?\s*종료(되었|됐)|"
    r"registration\s+(is\s+)?closed|applications?\s+(are|is)\s+closed)", re.I)

_host_lock = {}
_host_last = {}
_robots = {}
_glock = threading.Lock()


def _wait_host(host):
    with _glock:
        lk = _host_lock.setdefault(host, threading.Lock())
    lk.acquire()
    gap = HOST_GAP - (time.time() - _host_last.get(host, 0))
    if gap > 0:
        time.sleep(gap)
    return lk



def _http_only_opener():
    """http·https만 여는 opener. 기본 urlopen은 file://·ftp://·data:도 열 수 있어서,
    공고에 적힌 주소가 이상한 scheme이어도 서버 파일을 읽지 못하게 손잡이를 골라 끼운다."""
    op = urllib.request.OpenerDirector()
    for h in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(), urllib.request.HTTPHandler(),
              urllib.request.HTTPSHandler(), urllib.request.HTTPDefaultErrorHandler(),
              urllib.request.HTTPRedirectHandler(), urllib.request.HTTPErrorProcessor()):
        op.add_handler(h)
    return op


_OPENER = _http_only_opener()

def _robots_ok(url):
    p = urllib.parse.urlsplit(url)
    base = "%s://%s" % (p.scheme, p.netloc)
    with _glock:
        rp = _robots.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with _OPENER.open(req, timeout=8) as r:
                rp.parse(r.read(200_000).decode("utf-8", "replace").splitlines())
        except Exception:  # noqa: BLE001 - robots.txt가 없거나 못 열면 허용으로 본다
            rp.parse([])
        with _glock:
            _robots[base] = rp
    return rp.can_fetch(UA, url)


def page_text(raw, charset):
    s = raw.decode(charset or "utf-8", "replace")
    if "\ufffd" in s[:4000] and charset in (None, "utf-8"):
        try:
            s = raw.decode("cp949")
        except UnicodeDecodeError:
            pass
    # 숨긴 글(display:none 등)·스크립트는 공고문으로 쓰지 않는다
    s = re.sub(r"(?is)<(script|style|noscript|template|svg)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<([a-z0-9]+)[^>]*(display\s*:\s*none|visibility\s*:\s*hidden|aria-hidden=\"true\"|\shidden[\s>])[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = H.unescape(s)
    s = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_url(url):
    """한글 등 비ASCII 경로·질의를 퍼센트 인코딩(이미 인코딩된 %XX는 그대로)."""
    p = urllib.parse.urlsplit(url)
    host = p.hostname.encode("idna").decode("ascii") if p.hostname else ""
    netloc = host + (":%d" % p.port if p.port else "")
    return urllib.parse.urlunsplit((p.scheme, netloc, urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;="),
                                    urllib.parse.quote(p.query, safe="=&%:/?@!$'()*+,;"), ""))


def fetch(url):
    """→ (code, text). code 0 = 연결 실패·시간 초과, -1 = robots.txt가 막음."""
    if not url.startswith(("https://", "http://")):
        return 0, ""
    try:
        url = quote_url(url)
    except (ValueError, UnicodeError):
        return 0, ""
    if not _robots_ok(url):
        return -1, ""
    host = urllib.parse.urlsplit(url).netloc
    lk = _wait_host(host)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.5"})
        with _OPENER.open(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES)
            return r.status, page_text(raw, r.headers.get_content_charset())
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return 0, ""
    finally:
        _host_last[host] = time.time()
        lk.release()


def _key(t):
    return re.sub(r"[^0-9a-z가-힣]", "", (t or "").lower())


def closed_evidence(code, text, title):
    if code == 410:
        return "원문이 삭제됨(410)"
    if not text:
        return ""
    k = _key(title)[:10]
    flat = _key(text)
    if len(k) >= 6 and k in flat:
        m = CLOSED_PHRASES.search(text)
        if m:
            return "원문에 '%s'" % m.group(0).strip()[:30]
    return ""


def check_item(it):
    urls = []
    if it.get("official_url"):
        urls.append(it["official_url"])
    for s in it.get("sources") or []:
        if s.get("url") and s["url"] not in urls:
            urls.append(s["url"])
    best = {"code": 0, "url": urls[0] if urls else "", "text": ""}
    why = ""
    for u in urls[:3]:
        code, text = fetch(u)
        ev = closed_evidence(code, text, it.get("title"))
        if ev and not why:
            why = ev
        if 200 <= code < 400 and len(text) > len(best["text"]):
            best = {"code": code, "url": u, "text": text}
        elif not (200 <= best["code"] < 400) and code:
            best = {"code": code, "url": u, "text": best["text"]}
    return best, why


def atomic_json(path, obj):
    fd, tmp = tempfile.mkstemp(dir=str(Path(path).parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=str(ROOT / "site" / "data" / "items.json"))
    ap.add_argument("--state", default=str(OPS_ROOT / "state"))
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    state = Path(a.state)
    (state / "pages").mkdir(parents=True, exist_ok=True)
    items = json.loads(Path(a.items).read_text(encoding="utf-8"))
    todo = [it for it in items if it.get("status") != "마감"]
    if a.limit:
        todo = todo[:a.limit]
    try:
        links = json.loads((state / "links.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        links = {}
    today = today_kst().isoformat()
    t0 = time.time()
    done = [0]

    def run(it):
        r = check_item(it)
        done[0] += 1
        if done[0] % 50 == 0:
            print("  … %d/%d (%.0f초)" % (done[0], len(todo), time.time() - t0), flush=True)
        return r
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(run, todo))
    ok_n = bad_n = closed_n = 0
    for it, (best, why) in zip(todo, results):
        prev = links.get(it["id"]) or {}
        ok = 200 <= best["code"] < 400
        rec = {"url": best["url"], "code": best["code"], "ok": ok, "checked": today,
               "fails": 0 if ok else int(prev.get("fails", 0)) + 1}
        if why:
            rec["closed"] = True
            rec["why"] = why
            closed_n += 1
        links[it["id"]] = rec
        ok_n += ok
        bad_n += not ok
        if best["text"]:
            (state / "pages" / ("%s.txt" % it["id"])).write_text(best["text"][:6000], encoding="utf-8")
    # 목록에서 빠진 지 오래된 기록 정리
    keep = {it["id"] for it in items}
    links = {k: v for k, v in links.items() if k in keep}
    atomic_json(state / "links.json", links)
    print("%s 원문 확인 %d건: 열림 %d · 안 열림 %d · 마감 증거 %d (%.0f초)" % (
        now_kst().strftime("%F %T"), len(todo), ok_n, bad_n, closed_n, time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())

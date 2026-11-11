"""수집 공통 도구: https 전용 요청, 예절(간격·UA), 캐시, 경로."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
SITE_DATA = ROOT / "site" / "data"
KST = ZoneInfo("Asia/Seoul")

UA = "gongmo-private-bot/1.0 (+personal use)"
MIN_INTERVAL = 1.1  # 요청 사이 최소 간격(초)
_last_request = [0.0]

# https만 여는 요청기(file:// 등 다른 방식 차단)
_OPENER = urllib.request.OpenerDirector()
for _h in (urllib.request.HTTPSHandler, urllib.request.HTTPDefaultErrorHandler,
           urllib.request.HTTPRedirectHandler, urllib.request.HTTPErrorProcessor,
           urllib.request.UnknownHandler):
    _OPENER.add_handler(_h())


def now_kst():
    return datetime.now(KST)


def today_kst():
    return now_kst().date()


def _throttle():
    wait = MIN_INTERVAL - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.time()


def fetch(url, data=None, headers=None, retries=3, timeout=30, is_json=False):
    """https GET/POST. data가 있으면 POST. (상태, 본문텍스트)를 돌려준다."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("https 주소만 요청합니다: %s" % url)
    _throttle()
    body = None
    if data is not None:
        body = data.encode("utf-8") if isinstance(data, str) else urllib.parse.urlencode(data).encode("utf-8")
    hdrs = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs)
    last = (0, "")
    for attempt in range(retries):
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", errors="replace")
            if e.code < 500:
                return e.code, txt
            last = (e.code, txt)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = (0, str(e))
        time.sleep(2 * (attempt + 1))
    return last


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_iso_date(s):
    """여러 모양의 날짜 문자열을 date로. 실패하면 None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    # 2026-10-23 00:00:00.0 같은 꼬리 제거 후 재시도
    try:
        return datetime.strptime(s.split()[0].replace(".", "-")[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return None

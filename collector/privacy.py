"""공개 화면에 내보내기 전 개인 맥락 걷어내기.

검증 장부의 메모에는 운영자 개인 사정(호칭·소속·재직 형태·거주지·운영 서비스)이 섞일 수 있다.
사이트가 공개라서 그런 문장 조각(절)은 통째로 뺀다. 공모전 요강 자체(제목·주최)는 건드리지 않는다.
여러 번 돌려도 결과가 같다(멱등).
"""
import os
import re
from pathlib import Path

# 절(문장 조각) 단위로 지운다. 이 중 하나라도 들어 있으면 그 절을 뺀다.
# 여기에는 누구에게나 해당하는 '지원자·운영자 사정' 표현만 둔다. 운영자 본인을 알아볼 수 있는 낱말
# (호칭·기관 이름·거주지·나이 등)은 저장소 밖 파일에서 읽는다 — load_private_patterns() 참고.
_SENSITIVE = [
    r"알려진\s?\S*\s?(거주|재직)",
    r"미통지|통지\s?(보류|안\s?함)",
    r"현\s?사용자|사용자(에게|요청|\s?(연령|학생|학적|자격|사업자|수료|신분|현재))",
    r"소속\s?기관",
    r"소속\s?부서",
    r"소속\s?정책",
    r"(기관|업무|직무)\s?IP",
    r"(알려진|해당)\s?(사용자|지원자|운영자)|(사용자|지원자|운영자)(는|의|에게)\s",
    r"(사용자|지원자)\s?(이수|포함|해당|자격|나이|거주|신분|재학|재직)",
    r"추천(하지 않음|하지 않는다|함|한다)",
    r"내부\s?(확인|규정)",
    r"기관\s?(참가|참여)\S*\s?[·/,]?\s?상금",
    r"기관\s?(확인|규정)\s?(별도|필요)",
]


def _private_dir():
    """운영자 전용 설정 폴더. GONGMO_PRIVATE_DIR이 없으면 저장소의 private/(.gitignore로 빠짐)."""
    return Path(os.environ.get("GONGMO_PRIVATE_DIR") or Path(__file__).resolve().parent.parent / "private")


def load_private_patterns():
    """private/privacy-patterns.txt — 한 줄에 정규식 하나.
    'clause: <식>'은 그 절을 지우고, 'hard: <식>'은 제목·주최에 남으면 경고만 한다. '#'으로 시작하면 주석."""
    clause, hard = [], []
    try:
        lines = (_private_dir() / "privacy-patterns.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return clause, hard
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, pat = line.partition(":")
        pat = pat.strip()
        if not pat:
            continue
        (hard if kind.strip() == "hard" else clause).append(pat)
    return clause, hard


_EXTRA, _HARD = load_private_patterns()
_RE_SENSITIVE = re.compile("|".join("(?:%s)" % p for p in _SENSITIVE + _EXTRA))

# 공개 화면에 남기면 안 되는 낱말(제목·주최에 들어 있으면 경고만)
_RE_HARD = re.compile("|".join("(?:%s)" % p for p in _HARD)) if _HARD else None

# 절 나누기: ' · '(목록 이음), ';', 문장 끝 마침표(숫자 사이 소수점·URL은 제외), 줄바꿈
_RE_SPLIT = re.compile(r"(\s+·\s+|\s*[;；]\s*|(?<![0-9a-zA-Z])\.(?![0-9a-zA-Z])\s*|,\s+|\n+)")

# 헤르메스 메모 가운데 화면에 나오는 글 칸
HERMES_TEXT_KEYS = ("reason", "idea", "eligibility", "submission", "ip", "ai",
                    "restrictions", "fee", "burden")
# 장부에서 넘어와 개인 메모가 섞일 수 있는 항목 칸
ITEM_TEXT_KEYS = ("target_raw", "prize_text")


def scrub_text(text):
    """민감한 절을 뺀 글. 남는 게 없으면 ''."""
    if not text or not isinstance(text, str):
        return text
    if not _RE_SENSITIVE.search(text):
        return text
    # 괄호 안 덧말이 민감하면 괄호째 뺀다: '경남 도민만 가능(지원자 거주지는 해당 없음)'
    text = re.sub(r"\s?\(([^()]*)\)", lambda m: "" if _RE_SENSITIVE.search(m.group(1)) else m.group(0), text)
    if not _RE_SENSITIVE.search(text):
        return text.strip()
    parts = _RE_SPLIT.split(text)
    # split 결과: [절, 구분자, 절, 구분자, ...]
    out = []
    for i in range(0, len(parts), 2):
        clause = parts[i].strip(" \t·;；,/")
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if not clause:
            continue
        if _RE_SENSITIVE.search(clause):
            continue
        out.append((clause.strip(), sep))
    if not out:
        return ""
    s = ""
    for j, (clause, sep) in enumerate(out):
        s += clause
        if j < len(out) - 1:
            sep_clean = sep.strip()
            if sep_clean == "·":
                s += " · "
            elif sep_clean in (";", "；"):
                s += "; "
            elif sep_clean == ".":
                s += ". "
            elif sep_clean == ",":
                s += ", "
            else:
                s += " "
        else:
            # 원래 마침표로 끝났으면 살린다
            if sep.strip() == ".":
                s += "."
    s = re.sub(r"\s{2,}", " ", s).strip(" ;·,/")
    return s


def scrub_item(item):
    """항목 dict를 고쳐 돌려준다(제자리 수정)."""
    for k in ITEM_TEXT_KEYS:
        if isinstance(item.get(k), str):
            item[k] = scrub_text(item[k])
    hm = item.get("hermes")
    if isinstance(hm, dict):
        for k in HERMES_TEXT_KEYS:
            if isinstance(hm.get(k), str):
                hm[k] = scrub_text(hm[k])
    return item


def leftover_warnings(items):
    """다 걷어낸 뒤에도 남은 민감 낱말(제목·주최 등) 목록 — 사람이 볼 것."""
    warns = []
    for it in items:
        for k in ("title", "organizer"):
            v = it.get(k) or ""
            if _RE_HARD and _RE_HARD.search(v):
                warns.append("%s: %s=%s" % (it.get("id"), k, v[:60]))
    return warns


# ── 띄어쓰기 빠진 글 찾기 ───────────────────────────────
_RE_HANGUL = re.compile(r"[가-힣]")


def needs_spacing(text):
    """한글이 많은데 띄어쓰기가 거의 없는 글인지."""
    if not text or not isinstance(text, str):
        return False
    h = len(_RE_HANGUL.findall(text))
    if h < 12:
        return False
    if text.count(" ") / h < 0.08:
        return True
    # 군데군데만 띄운 글: 한 덩어리(공백 사이)에 한글이 12자 넘게 붙어 있으면
    return any(len(_RE_HANGUL.findall(tok)) >= 12 for tok in re.split(r"[\s·/+,;:()\[\]~]+", text))


def same_letters(a, b):
    """공백만 다르고 글자는 똑같은지(띄어쓰기 교정 검증용)."""
    return re.sub(r"\s+", "", a or "") == re.sub(r"\s+", "", b or "")

"""분야·참가대상 통일 매핑. 출처별 원문 분야 문자열을 공통 분야로 바꾼다."""
import re

# 통일 분야 14개(화면 칩 순서)
FIELDS = [
    "기획·아이디어",
    "광고·마케팅",
    "네이밍·슬로건",
    "IT·AI·데이터",
    "디자인·웹툰·캐릭터",
    "영상·사진·UCC",
    "문학·글·시나리오",
    "미술·음악·공연",
    "과학·공학",
    "논문·학술·리포트",
    "건축·건설·도시",
    "창업·비즈니스",
    "게임·SW",
    "기타",
]

# 원문 조각(소문자·공백무시) → 통일 분야. 순서대로 먼저 맞는 것.
_RULES = [
    (r"기획|아이디어|제안|정책|공공", "기획·아이디어"),
    (r"광고|마케팅|홍보|콘텐츠|cf|카피", "광고·마케팅"),
    (r"네이밍|슬로건|작명|이름", "네이밍·슬로건"),
    (r"ai|인공지능|데이터|빅데이터|해커톤|sw(?!c)|소프트|웹|모바일|플래시|it|코딩|프로그래밍|앱", "IT·AI·데이터"),
    (r"디자인|캐릭터|웹툰|만화|일러스트|ui|ux|편집|패션", "디자인·웹툰·캐릭터"),
    (r"영상|ucc|사진|포토|동영상|영화|비디오|촬영", "영상·사진·UCC"),
    (r"문학|글|시나리오|수기|수필|소설|시|에세이|글쓰기|독후감|스토리|작문|문예|웹소설", "문학·글·시나리오"),
    (r"미술|음악|예체능|공연|무용|미디어아트|작곡|노래|그림|회화|서예|예술", "미술·음악·공연"),
    (r"과학|공학|발명|기술|로봇|환경|에너지|화학|물리|바이오|농업|식품", "과학·공학"),
    (r"논문|리포트|학술|연구|보고서", "논문·학술·리포트"),
    (r"건축|건설|인테리어|도시|조경|공간", "건축·건설·도시"),
    (r"창업|비즈니스|사업|스타트업|경영|금융|투자", "창업·비즈니스"),
    (r"게임|소프트웨어", "게임·SW"),
]

# 화면에서 숨기는(공모전 아님) 분야 조각
_EXCLUDE = re.compile(r"대외활동|서포터즈|봉사|인턴|채용|취업특전|이벤트참여|경품")


def _norm(s):
    return re.sub(r"\s+", "", (s or "").lower())


def map_fields(raw_fields):
    """원문 분야 리스트/문자열 → 통일 분야 리스트(중복 제거, 순서 보존)."""
    if isinstance(raw_fields, str):
        parts = re.split(r"[,/·|]+", raw_fields)
    else:
        parts = []
        for x in (raw_fields or []):
            parts.extend(re.split(r"[,/·|]+", str(x)))
    out = []
    for p in parts:
        n = _norm(p)
        if not n:
            continue
        for pat, field in _RULES:
            if re.search(pat, n):
                if field not in out:
                    out.append(field)
                break
    if not out:
        out = ["기타"]
    return out


def looks_like_activity(raw_fields):
    """분야가 전부 대외활동·봉사 류인지(공모전이 아닐 수 있음)."""
    if isinstance(raw_fields, str):
        parts = re.split(r"[,/·|]+", raw_fields)
    else:
        parts = list(raw_fields or [])
    parts = [p for p in parts if _norm(p)]
    if not parts:
        return False
    return all(_EXCLUDE.search(p) for p in parts)


# 참가 대상 정규화 태그
_TARGET_RULES = [
    (r"누구나|제한\s*없|전체|일반\s*국민|대한민국\s*국민|모두", "누구나"),
    (r"대학원", "대학원생"),
    (r"대학생|대학", "대학생"),
    (r"고등|중학|청소년", "청소년"),
    (r"초등|어린이|유치", "어린이"),
    (r"일반인|성인", "일반인"),
    (r"직장|재직|기업\s*종사", "직장인"),
    (r"지역|거주|시민|도민|구민|군민", "지역제한"),
    (r"외국인|해외", "외국인"),
]


# 공모전이 아닌 모집(설문·체험단·서포터즈 등) 제목 신호
_NONCONTEST = re.compile(r"설문조사|만족도조사|수요조사|실태조사|체험단|서포터즈|기자단|홍보대사|모니터링단|모니터요원|평가단|기수모집|인턴|채용")
_CONTEST_WORD = re.compile(r"공모|대회|경진|콘테스트|챌린지|해커톤|공모전|작품|아이디어|경연|대전|어워드|awards?")


def is_non_contest(title):
    """제목만으로 공모전이 아님이 분명하면 True."""
    n = _norm(title)
    if _NONCONTEST.search(n):
        return True
    if "이벤트" in n and not _CONTEST_WORD.search(n):
        return True
    return False


def map_targets(raw_target):
    """참가 대상 원문 → 정규화 태그 리스트."""
    n = _norm(raw_target)
    out = []
    for pat, tag in _TARGET_RULES:
        if re.search(pat, n) and tag not in out:
            out.append(tag)
    return out

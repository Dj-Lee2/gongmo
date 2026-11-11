/* 공모모아 화면 로직 (바닐라 JS). 모든 텍스트는 이스케이프, 외부 링크는 https만 렌더.
 * 화면 상태(탭·검색어·분야·대상·정렬)는 주소 해시에 담는다 — 새로고침·뒤로 가기·링크 공유가 같은 화면으로 열린다. */
(function () {
  "use strict";
  var ITEMS = [], META = {}, FAV = loadFav(), FAVINFO = loadFavInfo(), TRACK = loadTrack();
  var DEFAULT = { tab: "open", q: "", fields: [], targets: [], sort: "deadline", due: "", id: "", view: "list", cm: "", cd: "", st: "" };
  var state = copyState(DEFAULT);
  var hideNo = load("gongmo.hideno") === "1"; // 내 조건에 안 맞는 공고 숨기기(이 기기에 기억)
  var opener = null; // 상세창을 연 요소(닫으면 초점을 돌려줌)
  var shownId = ""; // 지금 상세창에 보이는 공고(주소의 id와 따로 — 뒤로 가기로 주소가 먼저 바뀐다)
  var pushedDetail = false; // 상세를 열며 기록을 하나 쌓았는지(닫을 때 뒤로 가기로 되돌림)
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var $ = function (s, r) { return (r || document).querySelector(s); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function safeUrl(u) { return (typeof u === "string" && /^https:\/\//i.test(u)) ? u : null; }
  function nospace(s) { return String(s || "").replace(/\s+/g, "").toLowerCase(); }
  function copyState(s) { return { tab: s.tab, q: s.q, fields: s.fields.slice(), targets: s.targets.slice(), sort: s.sort, due: s.due, id: s.id, view: s.view, cm: s.cm, cd: s.cd, st: s.st }; }
  function hasCond() { return !!(state.q || state.fields.length || state.targets.length || state.due); }

  function store(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function loadFav() { try { return JSON.parse(load("gongmo.fav") || "[]"); } catch (e) { return []; } }
  // 관심 담기: id 목록 + 짧은 사본(제목·주최·기간·담은 날). 마감 뒤 자료에서 빠져도 관심 탭에 남고,
  // 담은 뒤 마감일이 바뀌면 알려 준다. 모두 이 기기에만 저장.
  function loadFavInfo() { try { return JSON.parse(load("gongmo.favinfo") || "{}") || {}; } catch (e) { return {}; } }
  function saveFav() { store("gongmo.fav", JSON.stringify(FAV)); store("gongmo.favinfo", JSON.stringify(FAVINFO)); }
  function isFav(id) { return FAV.indexOf(id) >= 0; }
  function snap(it) { return { t: it.title, o: it.organizer || "", s: it.start_date || "", e: it.end_date || "", at: todayKst() }; }
  function findItem(id) {
    var it = ITEMS.find(function (x) { return x.id === id; });
    return it || goneItems().find(function (x) { return x.id === id; }) || null;
  }
  function toggleFav(id) {
    var i = FAV.indexOf(id);
    if (i >= 0 && hasTrack(TRACK[id]) && !window.confirm("관심에서 빼면 이 공모전의 진행 기록(" + (stageLabel(stageOf(id)) || "메모") + ")도 지워집니다. 뺄까요?")) return false;
    if (i >= 0) { FAV.splice(i, 1); delete FAVINFO[id]; if (TRACK[id]) { delete TRACK[id]; saveTrack(); } }
    else {
      var it = ITEMS.find(function (x) { return x.id === id; });
      FAV.push(id); if (it) FAVINFO[id] = snap(it);
    }
    saveFav();
    return true;
  }
  // 같은 공모전 두 줄이 한 줄로 합쳐져 id가 바뀌면(aliases) 관심·진행 기록을 새 id로 옮긴다
  function migrateAliases() {
    var changed = false;
    ITEMS.forEach(function (it) {
      (it.aliases || []).forEach(function (old) {
        var i = FAV.indexOf(old);
        if (i < 0) return;
        if (isFav(it.id)) FAV.splice(i, 1); else FAV[i] = it.id;
        if (FAVINFO[old] && !FAVINFO[it.id]) FAVINFO[it.id] = FAVINFO[old];
        delete FAVINFO[old];
        if (TRACK[old] && !TRACK[it.id]) TRACK[it.id] = TRACK[old];
        delete TRACK[old];
        changed = true;
      });
    });
    if (changed) { saveFav(); saveTrack(); }
  }
  // 예전에 담아 사본이 없는 것은 지금 자료로 채운다
  function fillFavInfo() {
    var changed = false;
    FAV.forEach(function (id) {
      if (FAVINFO[id]) return;
      var it = ITEMS.find(function (x) { return x.id === id; });
      if (it) { FAVINFO[id] = snap(it); changed = true; }
    });
    if (changed) saveFav();
  }
  // 담았는데 지금 자료에 없는 것(원문에서 내려감) → 사본으로 목록 한 줄을 만든다
  function goneItems() {
    var have = {}; ITEMS.forEach(function (x) { have[x.id] = 1; });
    return FAV.filter(function (id) { return !have[id] && FAVINFO[id]; }).map(function (id) {
      var f = FAVINFO[id];
      return { id: id, title: f.t, organizer: f.o, start_date: f.s || null, end_date: f.e || null, status: "마감", dday: null,
        fields: [], target_tags: [], sources: [], gone: true };
    });
  }
  // 담은 뒤 마감일이 바뀌었는지: null | {from, to, later}
  function deadlineChange(it) {
    var f = FAVINFO[it.id];
    if (!f || it.gone || !f.e || !it.end_date || f.e === it.end_date) return null;
    return { from: f.e, to: it.end_date, later: it.end_date > f.e };
  }
  // ── 내 진행 기록: 관심 담은 공모전의 단계·제출일·발표일·메모(이 기기에만 저장) ──
  // gongmo.track = { id: { st: "prep"|"sent"|"win"|"lose", sent: "YYYY-MM-DD", res: "YYYY-MM-DD", memo: "", up: "YYYY-MM-DD" } }
  var STAGES = [
    { k: "", label: "관심만" }, { k: "prep", label: "준비 중" }, { k: "sent", label: "제출 완료" },
    { k: "win", label: "수상" }, { k: "lose", label: "탈락" }
  ];
  var STAGE_KEYS = ["none", "prep", "sent", "win", "lose"];
  function stageLabel(k) { for (var i = 0; i < STAGES.length; i++) if (STAGES[i].k === k) return STAGES[i].label; return ""; }
  function loadTrack() { try { var t = JSON.parse(load("gongmo.track") || "{}"); return t && typeof t === "object" ? t : {}; } catch (e) { return {}; } }
  function saveTrack() { store("gongmo.track", JSON.stringify(TRACK)); }

  // 예전 '기기 간 공유' 링크(#…&sync=코드)로 들어오면 코드를 주소에서 지운다(기능은 없앰 — 기록은 각 브라우저에만)
  function takeSyncFromHash() {
    ["gongmo.sync.key", "gongmo.sync.meta"].forEach(function (k) { store(k, null); });
    if (!/(?:^#|&)sync=/.test(location.hash)) return "";
    var rest = location.hash.replace(/^#/, "").split("&").filter(function (kv) { return kv.indexOf("sync=") !== 0; }).join("&");
    try { history.replaceState(null, "", location.pathname + location.search + (rest ? "#" + rest : "")); } catch (e) {}
    return "";
  }

  function trackOf(id) { return TRACK[id] || null; }
  function stageOf(id) { var t = TRACK[id]; return (t && t.st) || ""; }
  function hasTrack(t) { return !!(t && (t.st || t.sent || t.res || t.memo)); }
  // 기록을 바꾸면 관심에도 자동으로 담긴다
  function setTrack(id, patch) {
    var t = TRACK[id] || {};
    Object.keys(patch).forEach(function (k) { if (patch[k]) t[k] = patch[k]; else delete t[k]; });
    t.up = todayKst();
    if (hasTrack(t)) TRACK[id] = t; else delete TRACK[id];
    if (hasTrack(t) && !isFav(id)) toggleFav(id);
    saveTrack();
  }

  function md(d) { var m = /^\d{4}-(\d{2})-(\d{2})/.exec(d || ""); return m ? (+m[1]) + "." + (+m[2]) : d; }

  // ── 내 조건: 방문자가 고른 신분·출생연도·지역·관심 분야(이 브라우저에만 저장) → 공고마다 맞음/확인 필요/안 맞음 ──
  // 규칙으로만 가린다: 참가 대상 표시(target_tags), 지역 제한 + 공고 글의 시·도 이름, 공고 글의 나이 문구.
  var ROLES = [
    { k: "k12", label: "초중고생", tags: ["청소년", "어린이"] },
    { k: "univ", label: "대학생", tags: ["대학생"] },
    { k: "grad", label: "대학원생", tags: ["대학원생"] },
    { k: "worker", label: "직장인", tags: ["직장인", "일반인"] },
    { k: "general", label: "일반인", tags: ["일반인"] }
  ];
  var REGIONS = [
    ["서울", ["서울"]], ["부산", ["부산"]], ["대구", ["대구"]], ["인천", ["인천"]], ["광주", ["광주광역시", "광주시"]], ["대전", ["대전"]],
    ["울산", ["울산"]], ["세종", ["세종"]], ["경기", ["경기"]], ["강원", ["강원"]], ["충북", ["충북", "충청북도"]], ["충남", ["충남", "충청남도"]],
    ["전북", ["전북", "전라북도"]], ["전남", ["전남", "전라남도"]], ["경북", ["경북", "경상북도"]], ["경남", ["경남", "경상남도"]], ["제주", ["제주"]]
  ];
  var FIELD_LIST = ["기획·아이디어", "광고·마케팅", "네이밍·슬로건", "IT·AI·데이터", "디자인·웹툰·캐릭터", "영상·사진·UCC", "문학·글·시나리오",
    "미술·음악·공연", "과학·공학", "논문·학술·리포트", "건축·건설·도시", "창업·비즈니스", "게임·SW"];
  function loadMe() {
    try {
      var m = JSON.parse(load("gongmo.me") || "null") || {};
      return { roles: (m.roles || []).filter(function (k) { return ROLES.some(function (r) { return r.k === k; }); }),
        birth: /^(19|20)\d{2}$/.test(String(m.birth || "")) ? +m.birth : 0,
        region: REGIONS.some(function (r) { return r[0] === m.region; }) ? m.region : "",
        fields: (m.fields || []).filter(function (f) { return FIELD_LIST.indexOf(f) >= 0; }) };
    } catch (e) { return { roles: [], birth: 0, region: "", fields: [] }; }
  }
  var ME = loadMe();
  function saveMe() { store("gongmo.me", hasMe() ? JSON.stringify(ME) : null); }
  function hasMe() { return !!(ME.roles.length || ME.birth || ME.region || ME.fields.length); }
  function meText() {
    var p = ME.roles.map(function (k) { return ROLES.filter(function (r) { return r.k === k; })[0].label; });
    if (ME.birth) p.push(ME.birth + "년생");
    if (ME.region) p.push(ME.region);
    return p.concat(ME.fields).join(" · ");
  }
  // 공고 글의 나이 조건 → {min, max, birthFrom, birthTo, youth}
  function ageRule(text) {
    var t = String(text || ""), r = {}, m;
    if ((m = /(?:만\s?)?(\d{1,2})\s?세?\s?[~∼\-–]\s?(?:만\s?)?(\d{1,2})\s?세/.exec(t))) { r.min = +m[1]; r.max = +m[2]; }
    else {
      if ((m = /만\s?(\d{1,2})\s?세\s?(이하|미만)/.exec(t))) r.max = +m[1] - (m[2] === "미만" ? 1 : 0);
      if ((m = /만\s?(\d{1,2})\s?세\s?(이상|초과)/.exec(t))) r.min = +m[1] + (m[2] === "초과" ? 1 : 0);
    }
    if ((m = /((?:19|20)\d{2})\s?년?\s?[~∼\-–]\s?((?:19|20)\d{2})\s?년\s?(?:생|출생)/.exec(t))) { r.birthFrom = +m[1]; r.birthTo = +m[2]; }
    if (!("min" in r || "max" in r || "birthFrom" in r) && /청년/.test(t)) r.youth = true;
    return r;
  }
  // 결과: { level: "ok"|"check"|"no", why: [..] }
  function meMatch(it) {
    if (!hasMe()) return null;
    var why = [], level = "ok", tags = it.target_tags || [];
    function down(l, msg) { why.push(msg); if (l === "no" || (l === "check" && level === "ok")) level = l; }
    if (ME.roles.length) {
      var mine = [];
      ME.roles.forEach(function (k) { ROLES.forEach(function (r) { if (r.k === k) mine = mine.concat(r.tags); }); });
      if (!tags.length) down("check", "참가 대상 정보가 없어 원문 확인 필요");
      else if (tags.indexOf("누구나") < 0 && !tags.some(function (t) { return mine.indexOf(t) >= 0; }))
        down("no", "참가 대상: " + tags.filter(function (t) { return t !== "지역제한"; }).join("·"));
    }
    var text = (it.target_raw || "") + " " + (it.summary && it.summary.eligibility || "");
    if (tags.indexOf("지역제한") >= 0) {
      if (!ME.region) down("check", "지역 제한이 있는 공고");
      else {
        var al = REGIONS.filter(function (r) { return r[0] === ME.region; })[0][1];
        var hay = text + " " + (it.title || "") + " " + (it.organizer || "");
        if (!al.some(function (a) { return hay.indexOf(a) >= 0; })) down("check", "지역 제한 — " + ME.region + " 거주자도 되는지 원문 확인");
      }
    }
    if (ME.birth) {
      var ar = ageRule(text), y = +todayKst().slice(0, 4), hi = y - ME.birth, lo = hi - 1; // 만 나이는 lo~hi
      if ("max" in ar) { if (lo > ar.max) down("no", "나이: 만 " + ar.max + "세 이하"); else if (hi > ar.max) down("check", "나이 기준(만 " + ar.max + "세 이하) 경계"); }
      if ("min" in ar) { if (hi < ar.min) down("no", "나이: 만 " + ar.min + "세 이상"); else if (lo < ar.min) down("check", "나이 기준(만 " + ar.min + "세 이상) 경계"); }
      if ("birthFrom" in ar && (ME.birth < ar.birthFrom || ME.birth > ar.birthTo)) down("no", "출생연도: " + ar.birthFrom + "~" + ar.birthTo + "년생");
      if (ar.youth) down("check", "‘청년’ 대상 — 나이 기준 원문 확인");
    }
    return { level: level, why: why };
  }
  function meLevel(it) { var m = meMatch(it); return m ? m.level : ""; }
  function meFieldOk(it) { return !ME.fields.length || ME.fields.some(function (f) { return (it.fields || []).indexOf(f) >= 0; }); }

  var TABS = [
    { k: "open", ic: "🏠", label: "접수중" },
    { k: "soon", ic: "⏰", label: "마감 임박" },
    { k: "new", ic: "🆕", label: "오늘 새로" },
    { k: "upcoming", ic: "📅", label: "접수 예정" },
    { k: "me", ic: "🎯", label: "내 조건", hl: true },
    { k: "fav", ic: "⭐", label: "관심" },
    { k: "all", ic: "📚", label: "전체" },
    { k: "closed", ic: "🔒", label: "마감" }
  ];
  var TAB_KEYS = TABS.map(function (t) { return t.k; });
  var SORTS = ["deadline", "new", "prize"];

  // ── 주소 해시 ⇄ 상태 ──────────────────────────────
  // ── 주소 ⇄ 상태 ──
  // 목록: https://gongmo.orfa.shop/soon?q=… (접수중·조건 없음은 /)
  // 상세: https://gongmo.orfa.shop/c/<7자 코드> — 공모전마다 게시 때 만든 페이지(링크 미리보기에 제목이 뜸).
  //       목록 조건은 주소 대신 history.state.list에 두어 뒤로 가기·새로고침 때 되살린다.
  var CODE = {}, BYCODE = {}, BASE_TITLE = document.title;
  function codeOf(id) { return CODE[id] || ""; }
  function indexCodes() {
    CODE = {}; BYCODE = {};
    ITEMS.forEach(function (it) { if (it.code) { CODE[it.id] = it.code; BYCODE[it.code] = it.id; } });
  }
  // 목록 주소: 탭은 경로(/soon·/fav…, 접수중은 /), 달력은 뒤에 /cal, 검색·조건은 ?q=…&f=…&sort=…
  var TAB_PATH = /^\/(?:(soon|new|upcoming|me|hermes|fav|all|closed)(?:\/(cal))?|(cal))\/?$/;
  function urlOf(s) {
    var c = s.id && codeOf(s.id);
    return c ? "/c/" + c : listUrlOf(s);
  }
  function parseList(path, search) {
    var pre = copyState(DEFAULT), m = TAB_PATH.exec(path || "/");
    if (m) { if (m[1]) pre.tab = m[1] === "hermes" ? "me" : m[1]; if (m[2] || m[3]) pre.view = "cal"; } // 예전 /hermes → /me
    return readHash(String(search || "").replace(/^\?/, ""), pre);
  }
  function parseListUrl(u) { var i = u.indexOf("?"); return i < 0 ? parseList(u, "") : parseList(u.slice(0, i), u.slice(i)); }
  function hasLegacyHash() { return /^#(?:tab|q|f|t|sort|due|view|m|d|st|id)=/.test(location.hash); } // 예전 #tab=…&q=… 주소(#main 같은 앵커는 아님)
  function readUrl() {
    var hl = history.state && typeof history.state.list === "string" ? history.state.list : null, s;
    if (hl !== null) s = hl.charAt(0) === "#" ? readHash(hl) : parseListUrl(hl);
    else if (hasLegacyHash()) s = readHash(location.hash);
    else s = parseList(location.pathname, location.search);
    var m = /^\/c\/([a-z0-9]{5,16})\/?$/.exec(location.pathname);
    if (m) s.id = BYCODE[m[1]] || "gone-" + m[1];
    return s;
  }
  function readHash(hs, pre) {
    var s = pre || copyState(DEFAULT);
    var h = String(hs == null ? location.hash : hs).replace(/^#/, "");
    if (!h) return s;
    h.split("&").forEach(function (kv) {
      var i = kv.indexOf("="), k = i < 0 ? kv : kv.slice(0, i), v = "";
      try { v = i < 0 ? "" : decodeURIComponent(kv.slice(i + 1).replace(/\+/g, " ")); } catch (e) { return; }
      if (k === "tab" && v === "hermes") s.tab = "me";
      else if (k === "tab" && TAB_KEYS.indexOf(v) >= 0) s.tab = v;
      else if (k === "q") s.q = v.slice(0, 80);
      else if (k === "f" && v) s.fields = v.split(",").slice(0, 20);
      else if (k === "t" && v) s.targets = v.split(",").slice(0, 20);
      else if (k === "sort" && SORTS.indexOf(v) >= 0) s.sort = v;
      else if (k === "due" && v === "today") s.due = v;
      else if (k === "id" && /^[0-9a-f]{8,32}$/.test(v)) s.id = v;
      else if (k === "view" && v === "cal") s.view = v;
      else if (k === "m" && /^\d{4}-\d{2}$/.test(v)) s.cm = v;
      else if (k === "d" && /^\d{4}-\d{2}-\d{2}$/.test(v)) s.cd = v;
      else if (k === "st" && STAGE_KEYS.indexOf(v) >= 0) s.st = v;
    });
    if (s.view !== "cal") { s.cm = ""; s.cd = ""; }
    if (s.cd) s.cm = s.cd.slice(0, 7);
    return s;
  }
  function listUrlOf(s) {
    var p = [];
    if (s.q) p.push("q=" + encodeURIComponent(s.q));
    if (s.fields.length) p.push("f=" + encodeURIComponent(s.fields.join(",")));
    if (s.targets.length) p.push("t=" + encodeURIComponent(s.targets.join(",")));
    if (s.sort !== DEFAULT.sort) p.push("sort=" + s.sort);
    if (s.due) p.push("due=" + s.due);
    if (s.view === "cal") {
      if (s.cm && s.cm !== todayKst().slice(0, 7)) p.push("m=" + s.cm);
      if (s.cd) p.push("d=" + s.cd);
    }
    if (s.st && s.tab === "fav") p.push("st=" + s.st);
    if (s.id && !codeOf(s.id)) p.push("id=" + s.id); // 코드 없는 것(관심에만 남은 내려간 공고)만 예전 방식
    var path = "/" + (s.tab !== DEFAULT.tab ? s.tab : "");
    if (s.view === "cal") path += (path === "/" ? "" : "/") + "cal";
    return path + (p.length ? "?" + p.join("&") : "");
  }
  // push=true면 뒤로 가기로 돌아올 수 있게 기록을 남긴다(탭 바꾸기). 검색어 입력처럼 잦은 변화는 바꿔 쓰기만.
  function syncHash(push) {
    var url = urlOf(state), cur = location.pathname + location.search + location.hash;
    var detail = url.indexOf("/c/") === 0;
    var hst = detail ? { list: listUrlOf(Object.assign({}, state, { id: "" })) } : null;
    if (url === cur && JSON.stringify(history.state) === JSON.stringify(hst)) return;
    try { history[push ? "pushState" : "replaceState"](hst, "", url); } catch (e) {}
  }

  // ── 날짜(Asia/Seoul) ─────────────────────────────
  function todayKst() { return new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10); }
  function dayNum(dstr) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dstr || "");
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000 : null;
  }
  function daysTo(dstr) {
    var d = dayNum(dstr), t = dayNum(todayKst());
    return d == null ? null : d - t;
  }
  // 자료 갱신이 늦어도 D-day·상태는 보는 날 기준으로 맞춘다.
  function refreshDates(items, meta) {
    var fresh = meta && meta.generated_date === todayKst();
    items.forEach(function (it) {
      if (it.end_date && dayNum(it.end_date) != null) {
        it.dday = daysTo(it.end_date);
        if (it.dday < 0) it.status = "마감";
        else if (it.start_date && daysTo(it.start_date) > 0) it.status = "접수예정";
        else it.status = "접수중";
      }
      it.is_new_today = !!(fresh && it.is_new_today && it.status !== "마감"); // '오늘 새로'는 오늘 만든 자료일 때만
    });
  }
  // 같은 id가 두 번 오면 하나만(첫 번째) 남긴다 — 서버에서 합치지만 방어용
  function uniqById(items) {
    var seen = {};
    return items.filter(function (it) { if (seen[it.id]) return false; seen[it.id] = 1; return true; });
  }

  function ddayClass(it) {
    if (it.status === "마감") return "closed";
    if (it.status === "접수예정") return "soon-plan";
    var d = it.dday;
    if (d == null) return "ing";
    if (d <= 3) return "urgent";
    if (d <= 7) return "soon";
    return "ing";
  }
  function ddayText(it) {
    if (it.gone) return "내려감";
    if (it.status === "접수예정") {
      if (it.start_date) return "D-" + Math.max(0, daysTo(it.start_date)) + " 예정";
      return "접수예정";
    }
    if (it.status === "마감") return "마감";
    if (it.dday == null) return "접수중";
    if (it.dday === 0) return "오늘 마감";
    return "D-" + it.dday;
  }
  function prizeShort(it) {
    if (it.prize_total_won) {
      var w = it.prize_total_won;
      if (w >= 100000000) return (w / 100000000).toFixed(w % 100000000 ? 1 : 0) + "억원";
      return Math.round(w / 10000).toLocaleString() + "만원";
    }
    var p = (it.prize_text || "").trim();
    if (!p || /^(기타|미정|0)$/.test(p) || /^[\d,]+$/.test(p)) return "";
    return p;
  }

  function matchTab(it, tab) {
    switch (tab) {
      case "open": return it.status === "접수중";
      case "soon": return it.status === "접수중" && it.dday != null && it.dday >= 0 && it.dday <= 7;
      case "new": return !!it.is_new_today;
      case "upcoming": return it.status === "접수예정";
      case "me": return hasMe() && it.status !== "마감" && meLevel(it) !== "no" && meFieldOk(it);
      case "fav": return isFav(it.id);
      case "closed": return it.status === "마감";
      default: return true;
    }
  }
  function matchFilters(it) {
    if (state.q) {
      var q = nospace(state.q);
      var hay = nospace(it.title + " " + (it.organizer || "") + " " + (it.fields || []).join(" ") + " " + (it.target_raw || ""));
      if (hay.indexOf(q) < 0) return false;
    }
    if (state.fields.length && !state.fields.some(function (f) { return (it.fields || []).indexOf(f) >= 0; })) return false;
    if (state.targets.length && !state.targets.some(function (t) { return (it.target_tags || []).indexOf(t) >= 0; })) return false;
    if (state.due === "today" && !isDueToday(it)) return false;
    if (hideNo && state.tab !== "fav" && meLevel(it) === "no") return false;
    if (state.tab === "fav" && state.st && (state.st === "none" ? stageOf(it.id) !== "" : stageOf(it.id) !== state.st)) return false;
    return true;
  }
  function isDueToday(it) { return it.status === "접수중" && it.dday === 0; }

  function base() {
    var b = state.tab === "fav" ? ITEMS.concat(goneItems()) : ITEMS;
    return b.filter(function (it) { return matchTab(it, state.tab) && matchFilters(it); });
  }
  function calMonth() { return state.cm || todayKst().slice(0, 7); }
  // 진행 기록에 적은 결과 발표일(관심 담은 공모전, 탭·검색과 상관없이 내 일정이라 늘 보인다)
  function resByDay() {
    var out = {}, seen = {};
    ITEMS.concat(goneItems()).forEach(function (it) {
      var t = TRACK[it.id];
      if (!t || !t.res || seen[it.id] || !/^\d{4}-\d{2}-\d{2}$/.test(t.res)) return;
      seen[it.id] = 1;
      (out[t.res] = out[t.res] || []).push(it);
    });
    return out;
  }
  function current() {
    var list = base();
    if (state.view === "cal") { // 달력: 고른 날(없으면 보이는 달)에 마감하는 공고
      var m = calMonth();
      list = list.filter(function (it) { return it.end_date && (state.cd ? it.end_date === state.cd : it.end_date.slice(0, 7) === m); });
      if (state.cd) { // 고른 날 결과 발표가 있는 내 공모전도 함께
        var have = {};
        list.forEach(function (it) { have[it.id] = 1; });
        (resByDay()[state.cd] || []).forEach(function (it) { if (!have[it.id]) list.push(it); });
      }
    }
    list.sort(function (a, b) {
      if (state.sort === "prize") return (b.prize_total_won || 0) - (a.prize_total_won || 0);
      if (state.sort === "new") return (b.first_seen || "").localeCompare(a.first_seen || "") || cmpDeadline(a, b);
      return cmpDeadline(a, b);
    });
    return list;
  }
  function cmpDeadline(a, b) {
    var da = a.dday == null ? 99999 : a.dday, db = b.dday == null ? 99999 : b.dday;
    if (a.status === "마감") da += 100000; if (b.status === "마감") db += 100000;
    return da - db;
  }

  function renderTabs() {
    $("#tabs").innerHTML = TABS.map(function (t) {
      var n = t.k === "me" && !hasMe() ? "설정" : ITEMS.filter(function (it) { return matchTab(it, t.k); }).length + (t.k === "fav" ? goneItems().length : 0);
      return '<button class="tab' + (t.hl ? " hl" : "") + '" data-tab="' + t.k + '" aria-pressed="' +
        (state.tab === t.k) + '"><span class="tab-ic" aria-hidden="true">' + t.ic + "</span>" + esc(t.label) + ' <span class="tab-count">' + n + "</span></button>";
    }).join("");
    // 휴대폰에서 고른 탭이 탭 줄 밖에 있으면 보이게
    var sel = $('#tabs [aria-pressed="true"]'), bar = $("#tabs");
    if (sel) {
      var r = sel.getBoundingClientRect(), br = bar.getBoundingClientRect();
      if (r.left < br.left || r.right > br.right) bar.scrollLeft += (r.left - br.left) - 16;
    }
  }

  function renderChips() {
    $("#fieldChips").innerHTML = (META.fields || []).map(function (f) {
      return '<button class="chip" data-field="' + esc(f) + '" aria-pressed="' + (state.fields.indexOf(f) >= 0) + '">' + esc(f) + "</button>";
    }).join("");
    var targets = ["누구나", "대학생", "대학원생", "일반인", "청소년", "어린이", "직장인", "지역제한"];
    $("#targetChips").innerHTML = targets.map(function (t) {
      return '<button class="chip" data-target="' + esc(t) + '" aria-pressed="' + (state.targets.indexOf(t) >= 0) + '">' + esc(t) + "</button>";
    }).join("");
  }

  function badges(it) {
    var b = "", ch = isFav(it.id) && deadlineChange(it), tr = trackOf(it.id);
    if (tr && tr.st) b += '<span class="badge stage st-' + tr.st + '">' + esc(stageLabel(tr.st)) +
      (tr.st === "sent" && tr.res ? " · 발표 " + esc(md(tr.res)) : "") + "</span>";
    if (ch) b += '<span class="badge ' + (ch.later ? "later" : "earlier") + '">마감 ' + (ch.later ? "연장" : "앞당김") + " " + esc(md(ch.to)) + "</span>";
    if (it.is_new_today) b += '<span class="badge new">NEW!</span>';
    var lv = it.status !== "마감" && meLevel(it);
    if (lv === "ok") b += '<span class="badge me ok">✓ 내 조건</span>';
    else if (lv === "check") b += '<span class="badge me check">? 확인 필요</span>';
    else if (lv === "no") b += '<span class="badge me no">✕ 조건 안 맞음</span>';
    return b;
  }

  // 목록 한 줄: [D-day] [제목·주최] [분야·대상·표시] [상금·출처] [☆]
  function hrefOf(it) { return codeOf(it.id) ? "/c/" + codeOf(it.id) : "/#id=" + encodeURIComponent(it.id); }
  function rowHtml(it) {
    var fields = (it.fields || []).slice(0, 2).map(function (f) { return '<span class="tag field">' + esc(f) + "</span>"; }).join("");
    var tgt = (it.target_tags || []).slice(0, 2).map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("");
    var prize = prizeShort(it);
    var srcs = (it.sources || []).map(function (s) { return esc(s.name); }).join("·");
    var fav = isFav(it.id);
    return '<li class="row" data-id="' + esc(it.id) + '">' +
      '<span class="dday ' + ddayClass(it) + '">' + esc(ddayText(it)) + "</span>" +
      '<div class="row-main"><p class="row-tit" title="' + esc(it.title) + '"><a class="row-link" href="' + esc(hrefOf(it)) + '">' + esc(it.title) + "</a></p>" +
      '<div class="row-org">' + esc(it.organizer || "주최 미상") + "</div></div>" +
      '<div class="row-meta">' + fields + tgt + badges(it) + "</div>" +
      '<div class="row-side">' + (prize ? '<span class="row-prize">🏆 ' + esc(prize) + "</span>" : "") +
      '<span class="row-srcs">' + srcs + "</span></div>" +
      '<button class="fav' + (fav ? " on" : "") + '" data-fav="' + esc(it.id) + '" aria-label="관심 담기: ' + esc(it.title) + '" aria-pressed="' + fav + '">' +
      (fav ? "★" : "☆") + "</button></li>";
  }

  function emptyText() {
    if (state.tab === "fav" && FAV.length && state.st) return "‘" + (state.st === "none" ? "관심만" : stageLabel(state.st)) + "’ 단계인 공모전이 없습니다.";
    if (state.tab === "fav" && !FAV.length) return "아직 담은 공모전이 없습니다. 목록에서 ☆을 누르면 여기에 모입니다.";
    if (state.q) return "‘" + state.q + "’에 맞는 공모전이 없습니다. 검색어를 줄이거나 다른 탭에서 찾아보세요.";
    if (state.tab === "new") return "오늘 새로 들어온 공모전이 없습니다.";
    if (state.tab === "me" && !hasMe()) return "위에서 신분·나이·지역·관심 분야 중 하나 이상을 고르면 맞는 공고가 여기에 모입니다.";
    if (state.tab === "me") return "내 조건에 맞는 접수중 공고가 없습니다. 조건을 넓혀 보세요.";
    if (state.view === "cal") return state.cd ? "이날 마감하거나 결과가 나오는 공모전이 없습니다." : "이 달에 마감하는 공모전이 없습니다.";
    return "조건에 맞는 공모전이 없습니다.";
  }

  // 목록은 50건씩: 탭·검색·조건·정렬이 바뀌면 처음 50건으로, '더 보기'를 누르면 50건씩 늘린다.
  // 관심 담기처럼 같은 목록을 다시 그릴 때는 늘려 둔 만큼 그대로.
  var PAGE = 50, shown = PAGE, listKey = "";
  function render() {
    renderTabs(); renderChips(); renderMeBar(); renderToday(); renderCond(); renderView(); renderCal(); renderTrackBar(); renderHideNo();
    var list = current();
    var key = listUrlOf(Object.assign({}, state, { id: "" })) + "|" + hideNo;
    if (key !== listKey) {
      var first = !listKey; listKey = key; shown = PAGE;
      if (!first) { clearTimeout(render.t); var n = list.length; render.t = setTimeout(function () { announce("공모전 " + n + "건"); }, 700); }
    }
    $("#cards").innerHTML = list.slice(0, shown).map(rowHtml).join("");
    $("#count").textContent = list.length + "건";
    renderMore(list.length);
    var em = $("#empty");
    em.textContent = emptyText();
    if (!list.length && hasCond()) em.insertAdjacentHTML("beforeend", ' <button class="linkbtn" id="emptyClear" type="button">조건 지우기</button>');
    em.hidden = list.length > 0;
  }

  function renderMore(total) {
    var box = $("#more"), rest = total - Math.min(shown, total);
    box.hidden = rest <= 0;
    if (rest > 0) {
      box.innerHTML = '<button class="morebtn" id="moreBtn">더 보기 <span>' + Math.min(PAGE, rest) + "건</span></button>" +
        '<span class="more-n">' + Math.min(shown, total) + " / " + total + "건</span>";
    }
  }
  function showMore() {
    var first = shown; shown += PAGE;
    var list = current();
    $("#cards").insertAdjacentHTML("beforeend", list.slice(first, shown).map(rowHtml).join(""));
    renderMore(list.length);
    var row = $("#cards").children[first]; // 새로 붙은 첫 줄 제목으로 초점(키보드·화면 읽기)
    var link = row && row.querySelector("a.row-link");
    if (link) link.focus({ preventScroll: true });
    announce((list.length - Math.min(shown, list.length) > 0 ? "" : "마지막까지 ") + Math.min(shown, list.length) + "건 보는 중");
  }
  // 오늘 마감 줄: 0건이면 숨김. 누르면 오늘 마감만(접수중 탭), 다시 누르면 해제.
  function renderToday() {
    var n = ITEMS.filter(isDueToday).length, bar = $("#todayBar"), on = state.due === "today";
    bar.hidden = (!n && !on) || state.view === "cal" || state.tab === "fav"; // 달력엔 오늘 칸이, 관심 탭엔 진행 요약이 있어 감춘다
    bar.setAttribute("aria-pressed", String(on));
    bar.innerHTML = on ? "오늘 마감 <b>" + n + "건</b>만 보는 중 · 모두 보기"
                       : "⏰ 오늘 마감 <b>" + n + "건</b> 보기 ›";
  }
  // 건수 옆 조건 요약 + 한 번에 지우기(조건이 있을 때만)
  function renderHideNo() {
    var b = $("#hideNo");
    var n = hasMe() ? ITEMS.filter(function (it) { return it.status !== "마감" && meLevel(it) === "no" && matchTab(it, state.tab); }).length : 0;
    b.hidden = state.tab === "fav" || state.tab === "me" || !n;
    b.setAttribute("aria-pressed", String(hideNo));
    b.textContent = hideNo ? "조건 안 맞음 " + n + "건 숨김 · 보기" : "조건 안 맞음 " + n + "건 숨기기";
  }
  function renderCond() {
    var parts = [];
    if (state.due) parts.push("오늘 마감");
    if (state.q) parts.push("‘" + state.q + "’");
    parts = parts.concat(state.fields, state.targets);
    $("#cond").textContent = parts.join(" · ");
    $("#cond").hidden = !parts.length;
    $("#clearAll").hidden = !parts.length;
  }

  // 관심 탭 위 진행 요약: 단계별 건수(누르면 그 단계만) + 기록 백업·불러오기
  function renderTrackBar() {
    var bar = $("#trackBar");
    if (state.tab !== "fav") { bar.hidden = true; return; }
    bar.hidden = false;
    var all = ITEMS.concat(goneItems()).filter(function (it) { return isFav(it.id); }), cnt = { none: 0, prep: 0, sent: 0, win: 0, lose: 0 };
    all.forEach(function (it) { cnt[stageOf(it.id) || "none"]++; });
    var chips = [{ k: "", label: "전체", n: all.length }].concat(STAGES.map(function (s) { return { k: s.k || "none", label: s.label, n: cnt[s.k || "none"] }; }));
    bar.innerHTML = '<div class="tb-chips" role="group" aria-label="진행 단계">' + chips.map(function (c) {
      return '<button class="tb-chip' + (c.k && c.k !== "none" ? " st-" + c.k : "") + '" data-st="' + c.k + '" aria-pressed="' + (state.st === c.k) + '">' +
        esc(c.label) + " <b>" + c.n + "</b></button>";
    }).join("") + "</div>" +
      '<div class="tb-tools">' +
      '<button class="linkbtn" id="trackExport">기록 백업</button>' +
      '<button class="linkbtn" id="trackImport">불러오기</button><input type="file" id="trackFile" accept="application/json,.json" hidden></div>' +
      '<p class="tb-note">관심과 진행 기록은 이 브라우저에만 저장됩니다. 다른 기기로 옮길 때는 기록 백업 → 불러오기를 쓰세요.</p>';
  }
  function hhmm(ms) { var d = new Date(ms); return (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (d.getMinutes() < 10 ? "0" : "") + d.getMinutes(); }
  function exportTrack() {
    var data = { app: "gongmo", v: 1, at: new Date().toISOString(), fav: FAV, favinfo: FAVINFO, track: TRACK };
    var blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "gongmo-기록-" + todayKst() + ".json";
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    toast("기록 " + FAV.length + "건을 파일로 저장했습니다.");
  }
  // 불러오기는 합치기: 담은 목록은 합집합, 같은 공모전 기록은 더 최근에 바꾼 쪽
  function importTrack(file) {
    var rd = new FileReader();
    rd.onload = function () {
      var d; try { d = JSON.parse(rd.result); } catch (e) { d = null; }
      if (!d || d.app !== "gongmo" || !Array.isArray(d.fav)) { toast("공모모아 기록 파일이 아닙니다. '기록 백업'으로 받은 .json 파일을 골라 주세요.", true); return; }
      var added = 0;
      d.fav.forEach(function (id) {
        if (typeof id !== "string" || !/^[0-9a-f]{8,32}$/.test(id)) return;
        if (!isFav(id)) { FAV.push(id); added++; }
        var fi = d.favinfo && d.favinfo[id]; if (fi && !FAVINFO[id]) FAVINFO[id] = cleanSnap(fi);
        var tr = d.track && d.track[id];
        var ct = tr && cleanTrack(tr);
        if (ct && hasTrack(ct) && (!TRACK[id] || String(ct.up || "") > String(TRACK[id].up || ""))) TRACK[id] = ct;
      });
      saveFav(); saveTrack(); render();
      toast("불러왔습니다: 새로 담은 공모전 " + added + "건");
    };
    rd.readAsText(file);
  }
  function str(v, n) { return typeof v === "string" ? v.slice(0, n) : ""; }
  function dateOr(v) { return typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : ""; }
  function cleanSnap(f) { return { t: str(f.t, 200), o: str(f.o, 120), s: dateOr(f.s), e: dateOr(f.e), at: dateOr(f.at) }; }
  function cleanTrack(t) {
    var o = { st: ["prep", "sent", "win", "lose"].indexOf(t.st) >= 0 ? t.st : "", sent: dateOr(t.sent), res: dateOr(t.res), memo: str(t.memo, 500), up: dateOr(t.up) };
    Object.keys(o).forEach(function (k) { if (!o[k]) delete o[k]; }); return o;
  }

  // 상세창 '내 진행' 칸
  function trackHtml(it) {
    var t = trackOf(it.id) || {}, st = t.st || "";
    var h = '<div class="d-section d-track"><h3>내 진행</h3><div class="seg" role="group" aria-label="진행 단계">' + STAGES.map(function (s) {
      return '<button class="seg-b' + (s.k ? " st-" + s.k : "") + '" data-stage="' + s.k + '" aria-pressed="' + !!(st === s.k && (s.k || isFav(it.id))) + '">' + esc(s.label) + "</button>";
    }).join("") + "</div>";
    h += '<div class="tr-fields"><label>제출한 날<input type="date" id="trSent" value="' + esc(t.sent || "") + '"></label>' +
      '<label>결과 발표<input type="date" id="trRes" value="' + esc(t.res || "") + '"></label></div>' +
      '<label class="tr-memo">메모<textarea id="trMemo" rows="3" maxlength="500" placeholder="팀원, 제출물, 준비할 것 등">' + esc(t.memo || "") + "</textarea></label></div>";
    return h;
  }
  function bindTrack(it) {
    var box = $(".d-track"); if (!box) return;
    box.querySelector(".seg").onclick = function (e) {
      var b = e.target.closest("[data-stage]"); if (!b) return;
      var k = b.dataset.stage, patch = { st: k };
      if (k === "" && !isFav(it.id)) { toggleFav(it.id); }
      if ((k === "sent" || k === "win" || k === "lose") && !$("#trSent").value) { patch.sent = todayKst(); $("#trSent").value = patch.sent; }
      setTrack(it.id, patch);
      [].forEach.call(box.querySelectorAll("[data-stage]"), function (x) { x.setAttribute("aria-pressed", String(x.dataset.stage === k)); });
      var df = $("#dFav"); if (df) df.textContent = isFav(it.id) ? "★ 관심 담음" : "☆ 관심 담기";
      render();
    };
    $("#trSent").onchange = function () { setTrack(it.id, { sent: dateOr(this.value) }); render(); };
    $("#trRes").onchange = function () { setTrack(it.id, { res: dateOr(this.value) }); render(); };
    var tm = null;
    $("#trMemo").oninput = function () { var v = this.value; clearTimeout(tm); tm = setTimeout(function () { setTrack(it.id, { memo: v.slice(0, 500) }); }, 400); };
    $("#trMemo").onblur = function () { clearTimeout(tm); setTrack(it.id, { memo: this.value.slice(0, 500) }); render(); };
  }

  // ── 목록 / 달력 보기 ─────────────────────────────
  function renderView() {
    [].forEach.call(document.querySelectorAll("#viewSeg [data-view]"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.view === state.view));
    });
  }
  var WEEK = ["일", "월", "화", "수", "목", "금", "토"];
  function ymd(y, m, d) { return y + "-" + (m < 10 ? "0" : "") + m + "-" + (d < 10 ? "0" : "") + d; }
  function shiftMonth(m, k) {
    var y = +m.slice(0, 4), mo = +m.slice(5, 7) - 1 + k;
    y += Math.floor(mo / 12); mo = ((mo % 12) + 12) % 12;
    return y + "-" + (mo < 9 ? "0" : "") + (mo + 1);
  }
  // 마감 달력: 지금 탭·검색·분야·대상 조건을 그대로 따른다. 칸 = 그날 마감 건수(넓은 화면은 제목 두 개),
  // ★ = 관심 담은 공고 마감, 칸을 누르면 아래 목록이 그날 것만.
  function renderCal() {
    var box = $("#cal");
    if (state.view !== "cal") { box.hidden = true; return; }
    box.hidden = false;
    var m = calMonth(), y = +m.slice(0, 4), mo = +m.slice(5, 7), today = todayKst();
    var list = base(), byDay = {}, noDate = 0;
    list.forEach(function (it) {
      if (!it.end_date) { noDate++; return; }
      (byDay[it.end_date] = byDay[it.end_date] || []).push(it);
    });
    var monthN = 0, resDay = resByDay(), resN = 0;
    Object.keys(byDay).forEach(function (d) { if (d.slice(0, 7) === m) monthN += byDay[d].length; });
    Object.keys(resDay).forEach(function (d) { if (d.slice(0, 7) === m) resN += resDay[d].length; });
    var first = new Date(Date.UTC(y, mo - 1, 1)).getUTCDay(), days = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    var h = '<div class="cal-head"><button class="cal-nav" data-cal="prev" aria-label="이전 달">‹</button>' +
      '<h2 class="cal-tit">' + y + "년 " + mo + '월 <span class="cal-n">마감 ' + monthN + "건" + (resN ? " · 내 결과 발표 " + resN + "건" : "") + "</span></h2>" +
      '<button class="cal-nav" data-cal="next" aria-label="다음 달">›</button>' +
      (m !== today.slice(0, 7) ? '<button class="cal-today" data-cal="today">이번 달</button>' : "") + "</div>";
    h += '<div class="cal-grid" role="group" aria-label="' + y + "년 " + mo + '월 마감 달력">';
    WEEK.forEach(function (w, i) { h += '<div class="cal-wd' + (i === 0 ? " sun" : i === 6 ? " sat" : "") + '" aria-hidden="true">' + w + "</div>"; });
    // 이번 달은 지난 주(오늘이 든 주 앞)를 접어 빈 칸을 줄인다
    var startDay = 1;
    if (m === today.slice(0, 7)) {
      var td = +today.slice(8, 10);
      startDay = Math.max(1, td - ((first + td - 1) % 7));
    }
    var lead = startDay === 1 ? first : 0;
    if (startDay > 1) h += '<div class="cal-fold">' + mo + "월 1~" + (startDay - 1) + "일은 지난 날</div>";
    for (var i = 0; i < lead; i++) h += '<div class="cal-pad"></div>';
    for (var d = startDay; d <= days; d++) {
      var key = ymd(y, mo, d), arr = (byDay[key] || []).slice(), n = arr.length, rs = resDay[key] || [];
      var favN = arr.filter(function (it) { return isFav(it.id); }).length;
      arr.sort(function (a, b) { return (isFav(b.id) - isFav(a.id)) || ((meLevel(b) === "ok" ? 1 : 0) - (meLevel(a) === "ok" ? 1 : 0)); });
      var wd = (first + d - 1) % 7;
      var cls = "cal-day" + (n ? " has h" + (n >= 10 ? 3 : n >= 4 ? 2 : 1) : "") + (key === today ? " today" : "") +
        (key < today ? " past" : "") + (state.cd === key ? " sel" : "") + (wd === 0 ? " sun" : wd === 6 ? " sat" : "");
      if (rs.length && !n) cls += " has";
      var label = mo + "월 " + d + "일 " + WEEK[wd] + "요일" + (n ? ", 마감 " + n + "건" : ", 마감 없음") + (favN ? ", 관심 " + favN + "건" : "") +
        (rs.length ? ", 내 결과 발표 " + rs.length + "건" : "");
      h += '<button class="' + cls + '" data-day="' + key + '" aria-pressed="' + (state.cd === key) + '" aria-label="' + label + '"' + (n || rs.length ? "" : " disabled") + ">" +
        '<span class="cd-num">' + d + (favN ? '<span class="cd-fav" aria-hidden="true">★</span>' : "") + "</span>" +
        (n ? '<span class="cd-n">' + n + "<small>건</small></span>" : "") +
        (rs.length ? '<span class="cd-res" aria-hidden="true" title="' + esc(rs.map(function (it) { return it.title; }).join(", ")) + '">발표' +
          (rs.length > 1 ? " " + rs.length : "") + "</span>" : "") +
        (n ? '<span class="cd-items" aria-hidden="true">' + arr.slice(0, 2).map(function (it) {
          return '<span class="cd-it' + (isFav(it.id) ? " mine" : "") + '">' + esc(it.title) + "</span>";
        }).join("") + (n > 2 ? '<span class="cd-more">+' + (n - 2) + "건</span>" : "") + "</span>" : "") +
        "</button>";
    }
    h += "</div>";
    var sel = state.cd ? (+state.cd.slice(5, 7)) + "월 " + (+state.cd.slice(8, 10)) + "일 마감" + ((resDay[state.cd] || []).length ? "·결과 발표" : "") : mo + "월 마감 전체";
    h += '<div class="cal-foot"><span>' + esc(sel) + "</span>" +
      (state.cd ? '<button class="linkbtn" data-cal="all">' + mo + "월 전체 보기</button>" : "") +
      (noDate ? '<span class="cal-note">마감일이 정해지지 않은 ' + noDate + "건은 달력에 없습니다</span>" : "") + "</div>";
    box.innerHTML = h;
  }


  // ── 고르기 창(출생연도·사는 곳): 기본 <select> 대신 사이트 모양의 목록. 키보드 ↑↓←→·Home·End·Enter·Esc, 숫자·글자로 찾아가기 ──
  function pickHTML(id, label, opts, value, cols) {
    var cur = opts.filter(function (o) { return o[0] === value; })[0] || opts[0];
    return '<div class="pick" data-cols="' + cols + '"><span class="pick-label" id="' + id + 'L">' + esc(label) + "</span>" +
      '<button type="button" class="pick-btn' + (cur[0] ? " set" : "") + '" id="' + id + '" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="' + id + "L " + id + '">' +
      '<span class="pick-val">' + esc(cur[1]) + '</span><span class="pick-caret" aria-hidden="true">▾</span></button>' +
      '<ul class="pick-list" role="listbox" id="' + id + 'List" tabindex="-1" aria-labelledby="' + id + 'L" style="--cols:' + cols + '" hidden>' +
      opts.map(function (o, i) {
        var on = o[0] === cur[0];
        return '<li role="option" id="' + id + "O" + i + '" data-v="' + esc(o[0]) + '" aria-selected="' + on + '"' + (o[0] ? "" : ' class="none"') + ">" + esc(o[1]) + "</li>";
      }).join("") + "</ul></div>";
  }
  var pickTyped = "", pickTypedAt = 0;
  function pickOpen(btn) {
    pickCloseAll();
    var box = btn.parentNode, list = box.querySelector(".pick-list");
    list.hidden = false; btn.setAttribute("aria-expanded", "true"); box.classList.add("open");
    // 아래 자리가 모자라면(휴대폰 아래 탭 줄 포함) 위로 연다
    var r = btn.getBoundingClientRect(), below = window.innerHeight - r.bottom - (window.innerWidth < 640 ? 96 : 16);
    box.classList.toggle("up", below < Math.min(list.scrollHeight, 360) && r.top > below);
    var sel = list.querySelector('[aria-selected="true"]') || list.firstChild;
    pickActive(list, sel);
    list.focus({ preventScroll: true });
  }
  function pickActive(list, li) {
    if (!li) return;
    var old = list.querySelector(".act"); if (old) old.classList.remove("act");
    li.classList.add("act"); list.setAttribute("aria-activedescendant", li.id);
    var t = li.offsetTop, b = t + li.offsetHeight;
    if (t < list.scrollTop) list.scrollTop = t - 6; else if (b > list.scrollTop + list.clientHeight) list.scrollTop = b - list.clientHeight + 6;
  }
  function pickClose(box, focusBtn) {
    var list = box.querySelector(".pick-list"), btn = box.querySelector(".pick-btn");
    if (list.hidden) return;
    list.hidden = true; btn.setAttribute("aria-expanded", "false"); box.classList.remove("open", "up");
    if (focusBtn) btn.focus();
  }
  function pickCloseAll() {
    Array.prototype.forEach.call(document.querySelectorAll(".pick.open"), function (b) { pickClose(b, false); });
  }
  function pickChoose(box, li) {
    var id = box.querySelector(".pick-btn").id, v = li.dataset.v;
    pickClose(box, false);
    if (id === "meBirth") ME.birth = +v || 0;
    if (id === "meRegion") ME.region = v;
    meChanged();
    var again = $("#" + id); if (again) again.focus();
  }
  function pickKey(e, list) {
    var box = list.parentNode, items = Array.prototype.slice.call(list.children), cur = list.querySelector(".act"),
        i = Math.max(0, items.indexOf(cur)), cols = +box.dataset.cols || 1, n = i;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); pickClose(box, true); return; }
    if (e.key === "Tab") { pickClose(box, false); return; }
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (cur) pickChoose(box, cur); return; }
    if (e.key === "ArrowDown") n = i === 0 ? 1 : Math.min(items.length - 1, i + cols);
    else if (e.key === "ArrowUp") n = i <= cols ? 0 : i - cols;
    else if (e.key === "ArrowRight") n = Math.min(items.length - 1, i + 1);
    else if (e.key === "ArrowLeft") n = Math.max(0, i - 1);
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = items.length - 1;
    else if (e.key.length === 1 && /\S/.test(e.key)) {
      var now = Date.now(); pickTyped = (now - pickTypedAt > 900 ? "" : pickTyped) + e.key; pickTypedAt = now;
      var hit = items.filter(function (li) { return li.textContent.indexOf(pickTyped) === 0; })[0];
      if (hit) pickActive(list, hit);
      e.preventDefault(); return;
    } else return;
    e.preventDefault(); pickActive(list, items[n]);
  }

  // '내 조건' 탭 위 설정판: 고르면 바로 저장·반영
  function renderMeBar() {
    var bar = $("#meBar");
    if (state.tab !== "me") { bar.hidden = true; return; }
    bar.hidden = false;
    var y = +todayKst().slice(0, 4), years = [["", "선택 안 함"]];
    for (var yy = y - 10; yy >= 1940; yy--) years.push([String(yy), yy + "년생"]);
    var chip = function (attr, val, label, on) {
      return '<button type="button" class="chip" ' + attr + '="' + esc(val) + '" aria-pressed="' + on + '">' + esc(label) + "</button>";
    };
    bar.innerHTML =
      '<h2 class="me-tit">내 조건</h2>' +
      '<p class="me-note">고른 조건은 이 브라우저에만 저장됩니다. 공고의 참가 대상·지역·나이 문구로 자동으로 가르니, 지원 전에는 꼭 원문을 확인하세요.</p>' +
      '<div class="me-grid">' +
      '<div class="filter-group"><span class="filter-label" id="meRoleL">신분</span><div class="chips" role="group" aria-labelledby="meRoleL">' +
        ROLES.map(function (r) { return chip("data-me-role", r.k, r.label, ME.roles.indexOf(r.k) >= 0); }).join("") + "</div></div>" +
      '<div class="me-sel">' + pickHTML("meBirth", "출생연도", years, ME.birth ? String(ME.birth) : "", 4) +
        pickHTML("meRegion", "사는 곳", [["", "선택 안 함"]].concat(REGIONS.map(function (r) { return [r[0], r[0]]; })), ME.region, 3) + "</div>" +
      '<div class="filter-group"><span class="filter-label" id="meFieldL">관심 분야</span><div class="chips" role="group" aria-labelledby="meFieldL">' +
        FIELD_LIST.map(function (f) { return chip("data-me-field", f, f, ME.fields.indexOf(f) >= 0); }).join("") + "</div></div>" +
      "</div>" +
      (hasMe() ? '<p class="me-sum"><b>' + esc(meText()) + '</b> <button type="button" class="linkbtn" id="meReset">조건 모두 지우기</button></p>'
               : '<p class="me-sum">조건을 하나 이상 고르면 아래에 맞는 공고만 모입니다.</p>');
  }
  function meChanged() { saveMe(); render(); announce(hasMe() ? "내 조건에 맞는 공고 " + current().length + "건" : "내 조건을 지웠습니다"); }


  // 비슷한 공모전 3건. 점수 = 분야 겹침 3점(분야를 많이 단 공고일수록 나눠 깎음, '기타'는 1점)
  //   + 제목 낱말 겹침 2점씩(공모전·대회·모집·연도 같은 흔한 말 제외) + 대상이 하나라도 겹치면 1점.
  // 지금 접수중·예정만, 자기 자신·같은 제목 제외, 동점이면 접수중·마감 가까운 순.
  var STOP = /^(20\d\d|제\d+회|\d+회|공모전|공모|대회|경진대회|경연대회|경진|콘테스트|챌린지|해커톤|모집|참가자|참가|안내|및|the|of)$/;
  function words(t) {
    return (String(t || "").toLowerCase().match(/[0-9a-z가-힣]{2,}/g) || []).filter(function (w) { return !STOP.test(w); });
  }
  function similarHtml(it) {
    var key = function (t) { return nospace(t).replace(/[^0-9a-z가-힣]/g, ""); };
    var me = key(it.title), F = it.fields || [], T = it.target_tags || [], Wd = words(it.title);
    var scored = ITEMS.filter(function (x) { return x.id !== it.id && x.status !== "마감" && key(x.title) !== me; }).map(function (x) {
      var xf = x.fields || [], fs = 0, ws = 0;
      xf.forEach(function (f) { if (F.indexOf(f) >= 0) fs += f === "기타" ? 1 : 3; });
      fs = fs / Math.sqrt(Math.max(1, xf.length));
      words(x.title).forEach(function (w) { if (Wd.indexOf(w) >= 0) ws += 2; });
      var ts = (x.target_tags || []).some(function (t) { return T.indexOf(t) >= 0; }) ? 1 : 0;
      return { x: x, sc: fs + ws + ts, ok: fs >= 1.5 || ws > 0 };
    }).filter(function (o) { return o.ok; });
    scored.sort(function (a, b) {
      return b.sc - a.sc || (a.x.status === "접수중" ? 0 : 1) - (b.x.status === "접수중" ? 0 : 1) || cmpDeadline(a.x, b.x);
    });
    // 같은 대회가 출처마다 조금 다른 제목으로 두 번 잡힌 것은 하나만
    var top = [], seenKey = {};
    for (var i = 0; i < scored.length && top.length < 3; i++) {
      var k = key(scored[i].x.title).slice(0, 14);
      if (seenKey[k]) continue; seenKey[k] = 1; top.push(scored[i]);
    }
    if (!top.length) return "";
    return '<div class="d-section"><h3>비슷한 공모전</h3><ul class="sims">' + top.map(function (o) {
      var x = o.x;
      return '<li><button class="sim" data-sim="' + esc(x.id) + '"><span class="dday ' + ddayClass(x) + '">' + esc(ddayText(x)) + "</span>" +
        '<span class="sim-main"><span class="sim-tit">' + esc(x.title) + '</span><span class="sim-org">' + esc(x.organizer || "주최 미상") + "</span></span></button></li>";
    }).join("") + "</ul></div>";
  }

  function drow(label, val) {
    if (!val) return "";
    return "<dl class=\"d-row\"><dt>" + esc(label) + "</dt><dd>" + esc(val) + "</dd></dl>";
  }
  // fromHistory: 주소(뒤로 가기·공유 링크)로 연 경우 — 기록을 새로 쌓지 않는다
  // replace: 상세 안에서 다른 공고로 옮길 때 — 기록을 쌓지 않고 주소만 바꾼다(뒤로 가기 = 상세 닫기 유지)
  function openDetail(id, from, fromHistory, replace) {
    var it = findItem(id);
    if (!it) {
      closeDetail(true);
      if (state.id) { state.id = ""; syncHash(false); }
      if (fromHistory) toast("이 공고는 목록에서 내려갔습니다.");
      return;
    }
    if (!$("#drawer").hidden && shownId === id) return;
    shownId = id;
    document.title = it.title + " — 공모모아";
    opener = from || (fromHistory ? null : document.activeElement);
    if (replace) { state.id = id; syncHash(false); }
    else if (!fromHistory) { state.id = id; syncHash(true); pushedDetail = true; }
    var period = "";
    if (it.start_date || it.end_date) period = esc(it.start_date || "?") + " ~ " + esc(it.end_date || "?") + (it.end_time ? " " + esc(it.end_time) : "");
    var links = (it.sources || []).map(function (s) {
      var u = safeUrl(s.url);
      return u ? '<a class="btn" href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(s.name) + " 원문 ↗</a>" : "";
    }).join("");
    var official = safeUrl(it.official_url);
    var h = "";
    h += '<h2 class="d-title" id="dTitle">' + esc(it.title) + "</h2>";
    h += '<div class="d-org">' + esc(it.organizer || "주최 미상") + "</div>";
    h += '<div class="d-meta">' + (it.fields || []).map(function (f) { return '<span class="tag field">' + esc(f) + "</span>"; }).join("") +
      '<span class="dday ' + ddayClass(it) + '">' + esc(ddayText(it)) + "</span>" + badges(it) + "</div>";
    var ch = isFav(it.id) && deadlineChange(it);
    if (ch) h += '<div class="d-change ' + (ch.later ? "later" : "earlier") + '">담은 뒤 마감일이 ' + (ch.later ? "늦춰졌습니다" : "앞당겨졌습니다") +
      ": " + esc(ch.from) + " → " + esc(ch.to) + ' <button class="linkbtn" id="dAck">확인</button></div>';
    if (it.gone) h += '<div class="d-change">원문 사이트 목록에서 내려가 더 이상 모으지 않는 공고입니다. 담을 때 저장한 내용만 보입니다.</div>';
    if (it.closed_by) h += '<div class="d-change earlier">마감일 전이지만 원문에서 마감이 확인됐습니다: ' + esc(it.closed_by) + "</div>";
    else if (it.link_warn) h += '<div class="d-change">원문이 ' + esc(md(it.link_warn.checked)) + " 확인 때 열리지 않았습니다(" +
      esc(it.link_warn.code ? "응답 " + it.link_warn.code : "응답 없음") + "). 해외에서 막는 사이트일 수 있어 직접 열어 보세요.</div>";
    h += '<div class="d-actions">';
    if (official) h += '<a class="btn primary" href="' + esc(official) + '" target="_blank" rel="noopener noreferrer">공식 공고 보기 ↗</a>';
    h += '<button class="btn" id="dFav">' + (isFav(it.id) ? "★ 관심 담음" : "☆ 관심 담기") + "</button>";
    if (!it.gone) h += '<button class="btn" id="dShare">공유</button>';
    h += "</div>";
    h += trackHtml(it);
    h += '<div class="d-section">';
    h += drow("접수기간", period);
    h += drow("참가대상", it.target_raw);
    h += drow("상금", prizeShort(it));
    h += drow("상태", it.status);
    h += "</div>";
    if (it.summary && (it.summary.submission || it.summary.fee || (it.summary.eligibility && it.summary.eligibility !== it.target_raw))) {
      h += '<div class="d-section"><div class="d-sum"><h3>요강 요약</h3>';
      var elig = it.summary.eligibility && it.summary.eligibility !== it.target_raw ? it.summary.eligibility : ""; // 참가대상 칸과 같으면 한 번만
      [["참가 자격", elig], ["제출물", it.summary.submission], ["참가비", it.summary.fee]].forEach(function (p) {
        if (p[1]) h += '<div class="hk">' + esc(p[0]) + "</div><div>" + esc(p[1]) + "</div>";
      });
      h += '<div class="tri-foot">공고문을 자동으로 요약한 것입니다. 지원 전에 원문을 확인하세요.</div></div></div>';
    }
    var mm = meMatch(it);
    if (mm && it.status !== "마감") {
      var lab = { ok: "✓ 내 조건에 맞음", check: "? 원문 확인 필요", no: "✕ 내 조건과 안 맞음" }[mm.level];
      h += '<div class="d-section"><div class="d-me ' + mm.level + '"><h3>' + lab + "</h3>" +
        (mm.why.length ? "<ul>" + mm.why.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") + "</ul>" : "<p>참가 대상·지역·나이 문구에서 걸리는 점이 없습니다.</p>") +
        '<div class="tri-foot">내 조건(' + esc(meText()) + ")으로 자동 판단 · <a href=\"/me\" class=\"linkme\">조건 바꾸기</a></div></div></div>";
    }
    if (links) h += '<div class="d-section"><h3>원문·출처</h3><div class="d-actions">' + links + "</div></div>";
    if (!it.gone) h += similarHtml(it);
    $("#drawerBody").innerHTML = h;
    var df = $("#dFav");
    if (df) df.onclick = function () {
      if (toggleFav(it.id) === false) return;
      df.textContent = isFav(it.id) ? "★ 관심 담음" : "☆ 관심 담기";
      var keep = $("#drawerBody .d-track"); if (keep) { keep.outerHTML = trackHtml(it); bindTrack(it); }
      render();
    };
    bindTrack(it);
    if ($("#dShare")) $("#dShare").onclick = function () { share(it); };
    if ($("#dAck")) $("#dAck").onclick = function () {
      FAVINFO[it.id] = snap(it); saveFav(); var box = $(".d-change"); if (box) box.remove(); render();
    };
    $("#toTop").hidden = true;
    $("#drawer").hidden = false; document.body.classList.add("lock"); setInert(true);
    $(".drawer-panel").scrollTop = 0;
    $("#drawerClose").focus();
  }
  // fromHistory: 뒤로 가기로 닫힌 경우. 화면 단추로 닫으면 상세를 열며 쌓은 기록을 되돌린다.
  // 상세창이 열린 동안 뒤 화면은 inert(화면 읽기 가상 커서·Tab이 뒤로 새지 않게)
  function setInert(on) {
    [".skip", ".top", ".tabs", "#main", "#toTop"].forEach(function (sel) {
      var el = $(sel); if (!el) return;
      if (on) el.setAttribute("inert", ""); else el.removeAttribute("inert");
    });
  }
  function closeDetail(fromHistory) {
    if ($("#drawer").hidden) return;
    $("#drawer").hidden = true; document.body.classList.remove("lock"); shownId = ""; document.title = BASE_TITLE; setInert(false);
    if (!fromHistory && state.id) {
      state.id = "";
      if (pushedDetail) { pushedDetail = false; try { history.back(); } catch (e) { syncHash(false); } }
      else syncHash(false); // 공유 링크로 들어온 경우: 주소에서 id만 뺀다
    }
    if (fromHistory) pushedDetail = false;
    updateTop();
    // 그사이 목록을 다시 그려 연 요소가 사라졌으면 같은 id의 줄로 초점을 돌려준다
    var back = opener && document.contains(opener) ? opener : null;
    if (!back && opener) {
      var oid = opener.dataset && opener.dataset.id ? opener.dataset.id : (opener.closest && opener.closest("[data-id]") || {}).dataset;
      if (oid && typeof oid === "object") oid = oid.id;
      if (oid) back = document.querySelector('[data-id="' + oid + '"] a') || null;
    }
    if (back && back.focus) back.focus();
    opener = null;
  }
  function trapFocus(e) {
    if (e.key !== "Tab" || $("#drawer").hidden) return;
    var panel = $(".drawer-panel");
    var f = [].slice.call(panel.querySelectorAll('a[href], button:not([disabled]), [tabindex="0"]'));
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
  }

  function renderFoot() {
    var upd = META.generated_at ? META.generated_at.replace("T", " ").slice(0, 16) : "";
    var lag = META.generated_date ? -daysTo(META.generated_date) : 0;
    $("#updated").textContent = "마지막 갱신: " + upd + " (KST) · 총 " + ITEMS.length + "건" +
      (lag >= 2 ? " · 자료가 " + lag + "일 전 것이라 새 공고가 빠졌을 수 있습니다" : "");
    var src = META.sources || {};
    $("#srcStatus").innerHTML = Object.keys(src).map(function (k) {
      var s = src[k];
      return "<li><span class=\"dot " + (s.ok ? "" : "bad") + "\"></span>" + esc(k) + " " + (s.count || 0) + "건" +
        (s.kept_previous ? " (직전 유지)" : "") + "</li>";
    }).join("");
  }

  function applyControls() {
    $("#q").value = state.q; $("#qClear").hidden = !state.q;
    $("#sort").value = state.sort;
  }
  function setTab(k) {
    // 관심 탭은 내가 담은 전부를 보는 곳 — 다른 탭에서 걸어 둔 검색어·분야·대상 조건을 끌고 가지 않는다
    if (k === "fav" && state.tab !== "fav") { state.q = ""; state.fields = []; state.targets = []; state.due = ""; applyControls(); }
    state.tab = k; syncHash(true); render();
    var top = $(".tabs").getBoundingClientRect().top + window.scrollY;
    if (window.scrollY > top) window.scrollTo({ top: Math.max(0, top - 4), behavior: "smooth" });
  }
  function focusDay(key) { var b = $('#cal [data-day="' + key + '"]'); if (b) b.focus(); }
  // 처음 화면: 탭·검색·조건·정렬을 처음으로, 상세 닫고 맨 위로. 이미 처음 화면이면 맨 위로만.
  function goHome() {
    var isHome = listUrlOf(state) === "/" && $("#drawer").hidden;
    if (!isHome) {
      if (!$("#drawer").hidden) { $("#drawer").hidden = true; document.body.classList.remove("lock"); opener = null; pushedDetail = false; shownId = ""; document.title = BASE_TITLE; setInert(false); }
      state = copyState(DEFAULT); syncHash(true); applyControls(); render();
    }
    scrollTop(isHome);
  }
  function scrollTop(smooth) {
    window.scrollTo({ top: 0, behavior: smooth && !reduceMotion ? "smooth" : "auto" });
  }
  // 맨 위로: 화면 1.5장 아래에서 보이고, 하단 마지막 줄이 보이면(거기 글자 단추가 있음)·상세가 열리면 숨김
  var footSeen = false;
  function updateTop() {
    $("#toTop").hidden = !(window.scrollY > window.innerHeight * 1.5 && !footSeen && $("#drawer").hidden);
  }
  // 공유: 휴대폰 공유창 → 안 되면 링크 복사
  function share(it) {
    var url = location.origin + (codeOf(it.id) ? "/c/" + codeOf(it.id) : "/#id=" + it.id);
    var text = it.title + (it.end_date ? " (마감 " + it.end_date + ")" : "");
    if (navigator.share) {
      navigator.share({ title: it.title, text: text, url: url }).catch(function (e) { if (e && e.name !== "AbortError") copyLink(url); });
    } else copyLink(url);
  }
  function copyLink(url) {
    var done = function () { toast("링크를 복사했습니다."); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(done, function () { fallbackCopy(url) ? done() : toast("복사하지 못했습니다. 이 주소를 길게 눌러 복사하세요: " + url, true); });
    } else if (fallbackCopy(url)) done(); else toast("복사하지 못했습니다. 이 주소를 길게 눌러 복사하세요: " + url, true);
  }
  function fallbackCopy(t) {
    var ta = document.createElement("textarea"); ta.value = t; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
    var ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta); return ok;
  }
  // 알림: 화면 토스트(aria-hidden)와 화면 읽기용 상태 영역(#announce, 처음부터 비어 있는 채로 있음)을 따로 둔다.
  // 오류처럼 다음 행동이 필요한 글은 닫기 전까지 남긴다(sticky).
  var toastTimer = null, announceTimer = null;
  function announce(msg) {
    var a = $("#announce"); if (!a) return;
    a.textContent = ""; clearTimeout(announceTimer);
    announceTimer = setTimeout(function () { a.textContent = msg; }, 60);
  }
  function hideToast() { var t = $("#toast"); t.classList.remove("show", "sticky"); t.innerHTML = ""; }
  function toast(msg, sticky) {
    var t = $("#toast");
    t.innerHTML = '<span class="toast-msg"></span>' + (sticky ? '<button class="toast-x" type="button">닫기</button>' : "");
    t.firstChild.textContent = msg;
    t.classList.add("show"); t.classList.toggle("sticky", !!sticky);
    announce(msg);
    clearTimeout(toastTimer);
    if (!sticky) toastTimer = setTimeout(hideToast, 2400);
  }

  function setSize(big) {
    document.documentElement.setAttribute("data-size", big ? "large" : "");
    $("#sizeBtn").setAttribute("aria-pressed", String(big));
    store("gongmo.size", big ? "large" : null);
  }

  function bind() {
    $("#tabs").addEventListener("click", function (e) {
      var t = e.target.closest(".tab"); if (t) setTab(t.dataset.tab);
    });
    $("#fieldChips").addEventListener("click", chipHandler("fields", "field"));
    $("#targetChips").addEventListener("click", chipHandler("targets", "target"));
    var q = $("#q");
    q.addEventListener("input", function () { state.q = q.value; $("#qClear").hidden = !q.value; syncHash(false); render(); });
    $("#qClear").addEventListener("click", function () { q.value = ""; state.q = ""; $("#qClear").hidden = true; syncHash(false); render(); q.focus(); });
    $("#sort").addEventListener("change", function () { state.sort = $("#sort").value; syncHash(false); render(); });
    document.addEventListener("click", function (e) {
      // 제목 링크: 휠 클릭·Ctrl/⌘ 클릭은 브라우저에 맡겨 새 탭(/c/코드)으로, 그냥 누르면 이 화면에서 상세창
      var lm = e.target.closest("a.linkme");
      if (lm && e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) { e.preventDefault(); closeDetail(); setTimeout(function () { setTab("me"); }, 0); return; }
      var lk = e.target.closest("a.row-link, a.hc-tit");
      if (lk && (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)) return;
      if (lk) e.preventDefault();
      var fav = e.target.closest("[data-fav]");
      if (fav) { e.stopPropagation(); toggleFav(fav.dataset.fav); render(); return; }
      var card = e.target.closest("[data-id]");
      if (card && !card.closest("#drawer")) openDetail(card.dataset.id, card.querySelector("a.row-link, a.hc-tit") || card);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDetail();
      // PC: '/'를 누르면 검색칸으로(입력 중·상세창이 열려 있을 때는 그대로)
      if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && $("#drawer").hidden &&
          !(e.target.closest && e.target.closest("input, select, textarea"))) { e.preventDefault(); $("#q").focus(); $("#q").select(); }
      trapFocus(e);
    });
    $("#drawerBody").addEventListener("click", function (e) {
      var sm = e.target.closest("[data-sim]");
      if (sm) openDetail(sm.dataset.sim, opener, false, true);
    });
    $("#drawerDim").addEventListener("click", function () { closeDetail(); });
    $("#drawerClose").addEventListener("click", function () { closeDetail(); });
    $("#homeLink").addEventListener("click", function (e) {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // 새 탭 열기는 그대로
      e.preventDefault(); goHome();
    });
    $("#clearAll").addEventListener("click", function () {
      state.q = ""; state.fields = []; state.targets = []; state.due = "";
      syncHash(false); applyControls(); render();
    });
    $("#todayBar").addEventListener("click", function () {
      if (state.due) state.due = "";
      else { state.due = "today"; state.tab = "open"; }
      syncHash(true); render();
    });
    $("#viewSeg").addEventListener("click", function (e) {
      var b = e.target.closest("[data-view]"); if (!b || b.dataset.view === state.view) return;
      state.view = b.dataset.view; state.cm = ""; state.cd = ""; if (state.view === "cal") state.due = "";
      syncHash(true); render();
    });
    $("#cal").addEventListener("click", function (e) {
      var day = e.target.closest("[data-day]"), nav = e.target.closest("[data-cal]");
      if (day) { state.cd = state.cd === day.dataset.day ? "" : day.dataset.day; syncHash(false); render(); focusDay(day.dataset.day); return; }
      if (!nav) return;
      var k = nav.dataset.cal;
      if (k === "prev" || k === "next") { state.cm = shiftMonth(calMonth(), k === "prev" ? -1 : 1); state.cd = ""; }
      else if (k === "today") { state.cm = ""; state.cd = ""; }
      else if (k === "all") state.cd = "";
      syncHash(false); render();
      var again = $('#cal [data-cal="' + k + '"]') || $("#cal .cal-nav"); if (again) again.focus();
    });
    $("#hideNo").addEventListener("click", function () {
      hideNo = !hideNo; store("gongmo.hideno", hideNo ? "1" : null); render();
    });
    $("#trackBar").addEventListener("click", function (e) {
      var c = e.target.closest("[data-st]");
      if (c) { state.st = state.st === c.dataset.st ? "" : c.dataset.st; syncHash(false); render(); var again = $('#trackBar [data-st="' + state.st + '"]'); if (again) again.focus(); return; }
      if (e.target.closest("#trackExport")) exportTrack();
      if (e.target.closest("#trackImport")) $("#trackFile").click();
    });
    $("#trackBar").addEventListener("change", function (e) {
      if (e.target.id === "trackFile" && e.target.files && e.target.files[0]) { importTrack(e.target.files[0]); e.target.value = ""; }
    });
    $("#meBar").addEventListener("click", function (e) {
      var r = e.target.closest("[data-me-role]"), f = e.target.closest("[data-me-field]");
      if (r) { var k = r.dataset.meRole, i = ME.roles.indexOf(k); if (i >= 0) ME.roles.splice(i, 1); else ME.roles.push(k); meChanged(); var a = $('#meBar [data-me-role="' + k + '"]'); if (a) a.focus(); }
      if (f) { var v = f.dataset.meField, j = ME.fields.indexOf(v); if (j >= 0) ME.fields.splice(j, 1); else ME.fields.push(v); meChanged(); var b2 = $('#meBar [data-me-field="' + v + '"]'); if (b2) b2.focus(); }
      if (e.target.closest("#meReset")) { ME = { roles: [], birth: 0, region: "", fields: [] }; meChanged(); var c = $("#meBar .chip"); if (c) c.focus(); }
    });
    $("#meBar").addEventListener("click", function (e) {
      var pb = e.target.closest(".pick-btn"), li = e.target.closest(".pick-list [role=option]");
      if (pb) { if (pb.getAttribute("aria-expanded") === "true") pickClose(pb.parentNode, true); else pickOpen(pb); }
      if (li) pickChoose(li.closest(".pick"), li);
    });
    $("#meBar").addEventListener("keydown", function (e) {
      var list = e.target.closest(".pick-list");
      if (list) { pickKey(e, list); return; }
      var pb = e.target.closest(".pick-btn");
      if (pb && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); pickOpen(pb); }
    });
    $("#meBar").addEventListener("mousemove", function (e) {
      var li = e.target.closest(".pick-list [role=option]");
      if (li && !li.classList.contains("act")) pickActive(li.parentNode, li);
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".pick")) pickCloseAll(); });
    $("#meBar").addEventListener("focusout", function (e) {
      var box = e.target.closest(".pick");
      if (box && e.relatedTarget && !box.contains(e.relatedTarget)) pickClose(box, false);
    });
    // 다른 탭에서 기록·내 조건을 바꾸면 이 탭도 맞춘다
    window.addEventListener("storage", function (e) {
      if (["gongmo.fav", "gongmo.favinfo", "gongmo.track", "gongmo.me"].indexOf(e.key) < 0) return;
      FAV = loadFav(); FAVINFO = loadFavInfo(); TRACK = loadTrack(); ME = loadMe(); render();
    });
    $("#more").addEventListener("click", function (e) { if (e.target.closest("#moreBtn")) showMore(); });
    $("#toast").addEventListener("click", function (e) { if (e.target.closest(".toast-x")) hideToast(); });
    $("#empty").addEventListener("click", function (e) {
      if (e.target.closest("#emptyClear")) { $("#clearAll").click(); var q = $("#q"); if (q) q.focus(); }
      if (e.target.closest("#retryLoad")) location.reload();
    });
    $("#toTop").addEventListener("click", function () { scrollTop(true); });
    $("#footTop").addEventListener("click", function () { scrollTop(true); });
    var ticking = false;
    window.addEventListener("scroll", function () {
      if (ticking) return; ticking = true;
      requestAnimationFrame(function () { ticking = false; updateTop(); });
    }, { passive: true });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (en) { footSeen = en[0].isIntersecting; updateTop(); }).observe($(".foot-end"));
    }
    $("#sizeBtn").addEventListener("click", function () {
      setSize(document.documentElement.getAttribute("data-size") !== "large");
    });
    window.addEventListener("popstate", function () {
      var prev = listUrlOf(Object.assign({}, state, { id: "" }));
      state = readUrl();
      // 상세만 열고 닫힌 것이면 목록은 그대로(다시 그리면 초점을 돌려준 줄이 사라진다)
      if (listUrlOf(Object.assign({}, state, { id: "" })) !== prev) { applyControls(); render(); }
      if (state.id) openDetail(state.id, null, true); else closeDetail(true);
    });
  }
  function chipHandler(stateKey, dataKey) {
    return function (e) {
      var c = e.target.closest(".chip"); if (!c) return;
      var v = c.dataset[dataKey], arr = state[stateKey], i = arr.indexOf(v);
      if (i >= 0) arr.splice(i, 1); else arr.push(v);
      syncHash(false); render();
    };
  }

  // 휴대폰에서는 '정렬'을 건수 줄 오른쪽으로 옮겨 목록을 한 줄 위로 올린다(PC는 검색창 옆 그대로).
  function placeSort() {
    var sort = $(".sort"), mobile = window.matchMedia("(max-width: 639px)").matches;
    var target = mobile ? $(".result-head") : $(".search-row");
    if (sort.parentNode !== target) target.appendChild(sort);
  }

  function boot() {
    if (load("gongmo.size") === "large") setSize(true);
    placeSort();
    var mq = window.matchMedia("(max-width: 639px)");
    if (mq.addEventListener) mq.addEventListener("change", placeSort); else if (mq.addListener) mq.addListener(placeSort);
    var linkKey = takeSyncFromHash();
    state = hasLegacyHash() ? readHash() : parseList(location.pathname, location.search); // 자료를 받기 전 임시(상세 코드는 자료를 받은 뒤 readUrl로)
    Promise.all([
      fetch("/data/meta.json").then(function (r) { return r.json(); }),
      fetch("/data/items.json").then(function (r) { return r.json(); })
    ]).then(function (res) {
      META = res[0]; ITEMS = uniqById(res[1] || []);
      indexCodes();
      state = readUrl();
      refreshDates(ITEMS, META);
      migrateAliases();
      fillFavInfo();
      bind(); applyControls(); renderFoot(); render();
      if (state.id) openDetail(state.id, null, true); // 공유 링크로 들어옴
      syncHash(false); // 예전 #tab=…·#id= 주소를 새 모양(/soon?q=…, /c/코드)으로 바꿔 쓴다
    }).catch(function (err) {
      $("#count").textContent = "";
      var em = $("#empty");
      em.textContent = "공모전 자료를 불러오지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요. ";
      em.insertAdjacentHTML("beforeend", '<button class="linkbtn" id="retryLoad" type="button">다시 시도</button>');
      em.hidden = false;
      em.addEventListener("click", function (e) { if (e.target.closest("#retryLoad")) location.reload(); });
      console.error(err);
    });
  }
  boot();
})();

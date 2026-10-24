"""알레르겐 매칭: 원재료 원문 문자열 -> 위험/주의/안전 판정.

DB·네트워크에 의존하지 않는 순수 함수다. 사전(Dictionary)만 받아서 계산한다.

판정 규칙 (기능 명세 F-06, 데이터 모델 term_rules)
  danger  : 선택한 알레르겐이 원재료에 직접 매칭 (복합원재료 유무와 무관)
  caution : 원재료 데이터가 없음 / 복합·모호 원재료가 있음 / 향료에서만 매칭
  safe    : 위 어느 것도 아님
  * 선택한 알레르겐이 하나도 없으면 ValueError (API 는 400 으로 바꿔 돌려준다)

매칭 방식
  1) 선택한 알레르겐의 동의어가 원문에 나타나는 모든 위치를 찾는다 (start/end 는 원문 기준)
  2) 그 알레르겐의 '제외어'와 겹치는 위치는 버린다  (제외어는 알레르겐별)
  3) 한 글자 키워드(BOUNDARY_KEYWORDS)는 앞뒤가 한글이 아닐 때만 인정한다
  4) 한 알레르겐 안에서 겹치는 위치는 가장 긴 키워드로 병합한다
  5) 향료($향 등) 성분 안의 매칭은 danger -> caution 으로 낮춘다
  6) 하위 성분이 펼쳐지지 않은 복합/모호 원재료는 unresolved 로 따로 담는다
     (뒤에 괄호로 성분이 나열돼 있으면 펼쳐진 것으로 보고 unresolved 로 보지 않는다)
"""
from __future__ import annotations

import json
import re
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 오탐이 잦은 한 글자 키워드. 앞뒤 글자가 한글이면 다른 단어의 일부로 보고 버린다.
# (게르마늄·맛있게, 잣나무, 굴비·토굴 ...) 콩·밀·닭은 '풋콩', '볶은밀' 같은 정상 표기가 있어 제외했다.
BOUNDARY_KEYWORDS = frozenset({"게", "잣", "굴"})

_HANGUL = re.compile(r"[가-힣]")
_OPEN, _CLOSE = "([{（［", ")]}）］"
_SEPARATORS = ",，、"
_EXPANDED = re.compile(r"[(\[{（［]\s*[^\s)\]}）］]")


@dataclass
class Dictionary:
    names: dict[str, str]                       # code -> 한글명
    keywords: dict[str, list[str]]              # code -> 동의어
    exclusions: dict[str, list[str]]            # code -> 제외어
    rules: list[tuple[str, str]] = field(default_factory=list)  # (pattern, rule_type)

    @staticmethod
    def from_seed(path: str | Path) -> "Dictionary":
        seed = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = [(k["allergen_code"], k["keyword"], k["is_exclusion"]) for k in seed["allergen_keywords"]]
        return Dictionary._build([(a["code"], a["name_ko"]) for a in seed["allergens"]], rows,
                                 [(r["pattern"], r["rule_type"]) for r in seed["term_rules"]])

    @staticmethod
    def from_db(conn) -> "Dictionary":
        from sqlalchemy import text
        allergens = [tuple(r) for r in conn.execute(text("select code, name_ko from allergens order by id"))]
        kws = [tuple(r) for r in conn.execute(text(
            "select a.code, k.keyword, k.is_exclusion from allergen_keywords k "
            "join allergens a on a.id = k.allergen_id order by k.id"))]
        rules = [tuple(r) for r in conn.execute(text("select pattern, rule_type from term_rules order by id"))]
        return Dictionary._build(allergens, kws, rules)

    @staticmethod
    def _build(allergens, kws, rules) -> "Dictionary":
        d = Dictionary({c: n for c, n in allergens},
                       {c: [] for c, _ in allergens}, {c: [] for c, _ in allergens}, list(rules))
        for code, kw, is_exc in kws:
            (d.exclusions if is_exc else d.keywords)[code].append(kw)
        return d


@dataclass
class Match:
    allergen: str          # 코드 (MILK ...)
    name_ko: str
    keyword: str           # 매칭된 동의어(병합된 구간에서 가장 긴 것)
    start: int             # 원문 기준 [start, end)
    end: int
    level: str             # danger | caution(향료 안에서만 매칭)
    ingredient: str        # 매칭이 속한 원재료 한 덩어리
    reason: str | None = None   # 'flavor' 또는 None


@dataclass
class Unresolved:
    pattern: str
    rule_type: str         # compound | ambiguous
    text: str
    start: int
    end: int


@dataclass
class Verdict:
    verdict: str                                  # danger | caution | safe
    matched: list[Match] = field(default_factory=list)
    allergens: list[dict] = field(default_factory=list)   # 알레르겐별 1회: {code, name_ko, level}
    unresolved: list[Unresolved] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)      # direct_match / flavor / compound / ambiguous / no_raw_material

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Segment:
    start: int
    end: int
    text: str
    name: str            # 괄호 앞 이름
    expanded: bool       # 괄호로 하위 성분이 나열됨


def split_ingredients(raw: str) -> list[_Segment]:
    """최상위 쉼표로 원재료를 나눈다 (괄호 안의 쉼표는 나누지 않는다)."""
    segs, depth, begin = [], 0, 0

    def push(b: int, e: int):
        chunk = raw[b:e]
        stripped = chunk.strip()
        if not stripped:
            return
        s = b + (len(chunk) - len(chunk.lstrip()))
        m = re.search(r"[(\[{（［]", stripped)
        name = (stripped[:m.start()] if m else stripped).strip()
        rest = stripped[m.start():] if m else ""
        segs.append(_Segment(s, s + len(stripped), stripped, name, bool(_EXPANDED.search(rest))))

    for i, ch in enumerate(raw):
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth = max(0, depth - 1)
        elif ch in _SEPARATORS and depth == 0:
            push(begin, i)
            begin = i + 1
    push(begin, len(raw))
    return segs


def _find_all(text: str, sub: str):
    i = text.find(sub)
    while i != -1:
        yield i, i + len(sub)
        i = text.find(sub, i + 1)


def _rule_hits(name: str, pattern: str) -> bool:
    return name.endswith(pattern[1:]) if pattern.startswith("$") else pattern in name


def _boundary_ok(raw: str, s: int, e: int) -> bool:
    before = raw[s - 1] if s > 0 else ""
    after = raw[e] if e < len(raw) else ""
    return not (before and _HANGUL.match(before)) and not (after and _HANGUL.match(after))


def _occurrences(raw: str, code: str, d: Dictionary) -> list[tuple[int, int, str]]:
    excl = [span for x in d.exclusions.get(code, []) for span in _find_all(raw, x)]
    found = []
    for kw in d.keywords.get(code, []):
        for s, e in _find_all(raw, kw):
            if any(s < ee and es < e for es, ee in excl):        # 제외어와 겹침
                continue
            if kw in BOUNDARY_KEYWORDS and not _boundary_ok(raw, s, e):
                continue
            found.append((s, e, kw))
    # 겹치는 구간 병합: 시작순, 같으면 긴 것 먼저
    found.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    merged: list[list] = []
    for s, e, kw in found:
        if merged and s < merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
            if len(kw) > len(merged[-1][2]):
                merged[-1][2] = kw
        else:
            merged.append([s, e, kw])
    return [(s, e, kw) for s, e, kw in merged]


def judge(raw_material: str | None, selected: list[str], d: Dictionary) -> Verdict:
    selected = [c for c in dict.fromkeys(selected) if c in d.names]
    if not selected:
        raise ValueError("선택된 알레르겐이 없습니다.")
    raw = raw_material or ""
    if not raw.strip():
        return Verdict("caution", reasons=["no_raw_material"])

    segs = split_ingredients(raw)
    starts = [s.start for s in segs]

    def seg_of(pos: int) -> _Segment | None:
        i = bisect_right(starts, pos) - 1
        return segs[i] if i >= 0 and pos < segs[i].end else None

    flavor_rules = [p for p, t in d.rules if t == "flavor"]
    matches: list[Match] = []
    for code in selected:
        for s, e, kw in _occurrences(raw, code, d):
            seg = seg_of(s)
            is_flavor = bool(seg) and any(_rule_hits(seg.name, p) for p in flavor_rules)
            matches.append(Match(code, d.names[code], kw, s, e,
                                 "caution" if is_flavor else "danger",
                                 seg.text if seg else "", "flavor" if is_flavor else None))
    matches.sort(key=lambda m: (m.start, m.allergen))

    unresolved: list[Unresolved] = []
    for seg in segs:
        if seg.expanded:
            continue
        for rtype in ("compound", "ambiguous"):          # compound 우선
            hit = next((p for p, t in d.rules if t == rtype and _rule_hits(seg.name, p)), None)
            if hit:
                unresolved.append(Unresolved(hit, rtype, seg.text, seg.start, seg.end))
                break

    # 알레르겐별 1회: danger 가 하나라도 있으면 danger
    order: dict[str, dict] = {}
    for m in matches:
        cur = order.setdefault(m.allergen, {"code": m.allergen, "name_ko": m.name_ko, "level": "caution"})
        if m.level == "danger":
            cur["level"] = "danger"

    reasons = []
    if any(m.level == "danger" for m in matches):
        reasons.append("direct_match")
    if any(m.level == "caution" for m in matches):
        reasons.append("flavor")
    for t in ("compound", "ambiguous"):
        if any(u.rule_type == t for u in unresolved):
            reasons.append(t)

    if "direct_match" in reasons:
        verdict = "danger"
    elif reasons:
        verdict = "caution"
    else:
        verdict = "safe"
    return Verdict(verdict, matches, list(order.values()), unresolved, reasons)

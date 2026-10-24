"""매칭 함수 단위 테스트. DB 없이 backend/DB/seed.json 의 사전으로 실행한다."""
from pathlib import Path

import pytest

from app.services.matcher import Dictionary, judge, split_ingredients

SEED = Path(__file__).resolve().parents[1] / "DB" / "seed.json"
pytestmark = pytest.mark.skipif(not SEED.exists(), reason="backend/DB/seed.json 없음 (폴더 이동 확인)")

ALL = ["EGG", "MILK", "BUCKWHEAT", "PEANUT", "SOYBEAN", "WHEAT", "MACKEREL", "CRAB", "SHRIMP", "PORK",
       "PEACH", "TOMATO", "SULFITES", "WALNUT", "CHICKEN", "BEEF", "SQUID", "SHELLFISH", "OYSTER",
       "ABALONE", "MUSSEL", "PINENUT"]


@pytest.fixture(scope="module")
def d():
    return Dictionary.from_seed(SEED)


def codes(v):
    return [m.allergen for m in v.matched]


# ---------- 기본 판정 ----------
def test_safe(d):
    raw = "정제수, 갓, 대파, 양파, 마늘, 천일염, 무"          # 실제 제품: 동치미
    v = judge(raw, ALL, d)
    assert v.verdict == "safe" and not v.matched and not v.unresolved and v.reasons == []


def test_danger_direct_match(d):
    v = judge("밀가루, 정제수", ["WHEAT"], d)
    assert v.verdict == "danger" and v.reasons == ["direct_match"]
    m = v.matched[0]
    assert (m.keyword, m.start, m.end) == ("밀가루", 0, 3)


def test_positions_point_into_original_text(d):
    raw = "정제수,   탈지분유 , 설탕"
    m = judge(raw, ["MILK"], d).matched[0]
    assert raw[m.start:m.end] == "탈지분유"


def test_no_raw_material_is_caution(d):
    for raw in (None, "", "   "):
        v = judge(raw, ["MILK"], d)
        assert v.verdict == "caution" and v.reasons == ["no_raw_material"]


def test_empty_selection_raises(d):
    with pytest.raises(ValueError):
        judge("밀가루", [], d)


def test_unknown_codes_are_ignored_but_all_unknown_raises(d):
    assert judge("밀가루", ["WHEAT", "NOPE"], d).verdict == "danger"
    with pytest.raises(ValueError):
        judge("밀가루", ["NOPE"], d)


# ---------- 오탐 제외 ----------
def test_peanut_squash_is_not_peanut(d):
    assert judge("땅콩호박, 정제수", ["PEANUT"], d).verdict == "safe"
    v = judge("땅콩호박, 땅콩", ["PEANUT"], d)
    assert v.verdict == "danger" and [(m.start, m.end) for m in v.matched] == [(6, 8)]


def test_germanium_is_not_crab(d):
    assert judge("게르마늄효모, 정제수", ["CRAB"], d).verdict == "safe"
    assert judge("술지게미, 쌀", ["CRAB"], d).verdict == "safe"


def test_single_char_crab_needs_boundary(d):
    assert judge("정제수, 게, 소금", ["CRAB"], d).verdict == "danger"
    assert judge("맛있게만든소스원료", ["CRAB"], d).verdict == "safe"


def test_pinenut_vs_pine_tree(d):
    assert judge("잣나무추출물", ["PINENUT"], d).verdict == "safe"
    assert judge("잣, 설탕", ["PINENUT"], d).verdict == "danger"


def test_oyster_vs_gulbi(d):
    assert judge("굴비, 소금", ["OYSTER"], d).verdict == "safe"
    assert judge("굴, 소금", ["OYSTER"], d).verdict == "danger"


def test_pork_vs_jerusalem_artichoke(d):
    assert judge("돼지감자, 물", ["PORK"], d).verdict == "safe"


def test_exclusions_are_per_allergen_buckwheat_vs_wheat(d):
    # 메밀은 밀(WHEAT)의 제외어이면서 메밀(BUCKWHEAT)의 동의어다
    raw = "메밀가루, 메밀가루, 밀가루, 천일염"                  # 실제 제품: 메밀부침가루
    wheat = judge(raw, ["WHEAT"], d)
    assert [(m.start, m.end) for m in wheat.matched] == [(12, 15)]     # 세 번째(밀가루)만
    buck = judge(raw, ["BUCKWHEAT"], d)
    assert buck.verdict == "danger" and len(buck.matched) == 2
    assert judge("밀가루, 정제수", ["BUCKWHEAT"], d).verdict == "safe"
    assert judge("메밀가루, 정제수", ["WHEAT"], d).verdict == "safe"


def test_wheat_false_positives(d):
    for raw in ("아밀라아제", "호밀", "밀랍", "밀크초콜릿"):
        assert judge(raw, ["WHEAT"], d).verdict == "safe", raw


def test_milk_synonyms_and_exclusions(d):
    assert judge("탈지분유, 설탕", ["MILK"], d).verdict == "danger"          # 탈지분유 -> 우유
    assert judge("코코넛밀크, 설탕", ["MILK"], d).verdict == "safe"
    assert judge("코코아버터, 땅콩버터", ["MILK"], d).verdict == "safe"


def test_soy_vs_other_beans(d):
    assert judge("땅콩, 완두콩, 병아리콩", ["SOYBEAN"], d).verdict == "safe"
    assert judge("콩기름(대두유)", ["SOYBEAN"], d).verdict == "danger"
    assert judge("풋콩", ["SOYBEAN"], d).verdict == "danger"      # 한 글자 경계 규칙을 쓰지 않는 이유


# ---------- 동일 알레르겐 병합 ----------
def test_overlapping_keywords_merge_into_one_match(d):
    v = judge("탈지분유", ["MILK"], d)
    assert len(v.matched) == 1 and v.matched[0].keyword == "탈지분유"
    assert (v.matched[0].start, v.matched[0].end) == (0, 4)


def test_allergen_listed_once_even_if_matched_many_times(d):
    v = judge("우유, 탈지분유, 치즈, 버터", ["MILK"], d)
    assert len(v.matched) == 4 and len(v.allergens) == 1
    assert v.allergens[0] == {"code": "MILK", "name_ko": "우유", "level": "danger"}


# ---------- 복합원재료 / 모호 / 향료 ----------
def test_compound_only_is_caution(d):
    v = judge("건면, 채종유(유채유또는카놀라유), 혼합제제", ["WHEAT"], d)   # 실제 제품: 스파게티면
    assert v.verdict == "caution" and v.reasons == ["compound"]
    assert v.unresolved[0].text == "혼합제제"


def test_direct_match_beats_compound(d):
    v = judge("밀가루, 혼합제제", ["WHEAT"], d)
    assert v.verdict == "danger" and "compound" in v.reasons


def test_mixed_milk_powder_is_both_milk_and_compound(d):
    v = judge("혼합분유, 정제수", ["MILK"], d)
    assert v.verdict == "danger" and v.reasons == ["direct_match", "compound"]
    assert v.unresolved[0].pattern == "혼합분유"
    # 우유를 선택하지 않았다면 복합원재료로서 caution
    assert judge("혼합분유, 정제수", ["WHEAT"], d).verdict == "caution"


def test_expanded_compound_is_not_unresolved(d):
    assert judge("혼합제제(덱스트린, 정제수)", ["WHEAT"], d).verdict == "safe"
    v = judge("혼합제제(밀가루, 정제수)", ["WHEAT"], d)               # 괄호 안 성분도 매칭된다
    assert v.verdict == "danger" and not v.unresolved


def test_ambiguous_peanut_or_nuts(d):
    raw = "설탕, 땅콩 또는 견과류가공품"                              # 실제 제품 표기
    v = judge(raw, ["PEANUT"], d)
    assert v.verdict == "danger" and v.unresolved and v.unresolved[0].text == "땅콩 또는 견과류가공품"
    v2 = judge(raw, ["WALNUT"], d)                                    # 호두는 직접 매칭 없음, 모호 표기
    assert v2.verdict == "caution" and not v2.matched and v2.unresolved


def test_flavor_demotes_to_caution(d):
    v = judge("복숭아향, 구연산", ["PEACH"], d)
    assert v.verdict == "caution" and v.reasons == ["flavor"]
    assert v.matched[0].level == "caution" and v.matched[0].reason == "flavor"


def test_real_flavor_and_fruit_together_is_danger(d):
    v = judge("복숭아, 복숭아향, 설탕, 구연산", ["PEACH"], d)          # 실제 제품: 365품 리얼ICED 피치
    assert v.verdict == "danger"
    assert [m.level for m in v.matched] == ["danger", "caution"]
    assert v.allergens == [{"code": "PEACH", "name_ko": "복숭아", "level": "danger"}]


def test_flavor_of_unselected_allergen_is_ignored(d):
    assert judge("딸기향, 정제수", ["PEACH"], d).verdict == "safe"


# ---------- 분리 함수 ----------
def test_split_ignores_commas_inside_parentheses():
    raw = "과자(밀가루, 우유), 설탕"
    segs = split_ingredients(raw)
    assert [s.text for s in segs] == ["과자(밀가루, 우유)", "설탕"]
    assert segs[0].expanded and not segs[1].expanded
    assert raw[segs[1].start:segs[1].end] == "설탕"


def test_split_handles_unbalanced_parentheses():
    assert [s.text for s in split_ingredients("가), 나")] == ["가)", "나"]

"""해석기는 **모호하면 답하지 않는다** — 그리고 한정자를 실제로 쓴다.

**왜 이 파일이 있나 (2026-08-25 실측).** 첫 판은 `value_source` 의 한정자를 버리고
(`rpartition(".")` 로 심볼만 취함) `*.java` 전체에서 **첫 매치**를 돌려줬다. 대상 코드베이스를
실제로 재 보니:

  · 해석 가능한 상수 이름 364개 중 **80개가 두 파일 이상**에 있고, **40개는 값이 서로 달랐다.**
  · 존재하지 않는 클래스명(`SomeClass.MAX_PAGE_SIZE`)으로도 값이 나왔다.
  · 테스트 픽스처가 함께 훑여 `EMAIL` 이 `"test@example.com"` 으로 잡혔다.

그 값은 `claims/answer.py` 를 거쳐 *"현재 200 (**확실**: 코드 상수 …)"* 로 나간다. 즉 **가장
확신하는 문장이 가장 틀리기 쉬운 자리**였다. `claims` 가 0행이라 아직 아무도 받지 않았고,
그래서 지금이 고칠 때다.
"""

from __future__ import annotations

from pathlib import Path

from nexus.index.code_source import CodeValueResolver


def _java(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


# ── 모호성: 같은 이름 · 다른 값 ────────────────────────────────────────────────

def test_same_name_different_values_is_refused(tmp_path):
    """두 클래스가 같은 이름을 **다른 값**으로 가지면 답하지 않는다.

    옛 판은 `rglob` 순서가 고른 쪽을 확신하는 문장으로 내보냈다. 이 검사가 그것을 막는다.
    """
    _java(tmp_path, "a/Alpha.java", "class Alpha { public static final int LIMIT = 10; }")
    _java(tmp_path, "b/Beta.java", "class Beta { public static final int LIMIT = 99; }")

    r = CodeValueResolver(tmp_path).resolve("LIMIT")
    assert r.found is False
    assert "서로 다른 값" in r.reason
    assert "Alpha.java" in r.reason and "Beta.java" in r.reason


def test_same_name_same_value_still_resolves(tmp_path):
    """대조군 — 중복이라도 **값이 같으면** 답에 모호함이 없다. 여기서 거절하면 과잉이다."""
    _java(tmp_path, "a/Alpha.java", "class Alpha { public static final int LIMIT = 10; }")
    _java(tmp_path, "b/Beta.java", "class Beta { public static final int LIMIT = 10; }")

    r = CodeValueResolver(tmp_path).resolve("LIMIT")
    assert r.found and r.value == "10"


def test_qualifier_disambiguates(tmp_path):
    """한정자를 주면 그 클래스의 값을 낸다 — 모호함이 해소된다."""
    _java(tmp_path, "a/Alpha.java", "class Alpha { public static final int LIMIT = 10; }")
    _java(tmp_path, "b/Beta.java", "class Beta { public static final int LIMIT = 99; }")

    res = CodeValueResolver(tmp_path)
    assert res.resolve("Alpha.LIMIT").value == "10"
    assert res.resolve("Beta.LIMIT").value == "99"


# ── 한정자를 실제로 쓴다 ──────────────────────────────────────────────────────

def test_nonexistent_qualifier_is_not_found(tmp_path):
    """없는 클래스명으로는 값이 나오면 안 된다.

    옛 판은 한정자를 버렸기 때문에 `SomeClass.LIMIT` 이 태연히 `10` 을 냈다 — 실측된 동작이다.
    """
    _java(tmp_path, "a/Alpha.java", "class Alpha { public static final int LIMIT = 10; }")

    r = CodeValueResolver(tmp_path).resolve("SomeClassThatDoesNotExist.LIMIT")
    assert r.found is False
    assert "선언한 파일에는 없다" in r.reason


def test_qualifier_matches_a_nested_declaration(tmp_path):
    """파일명이 아니라 **안에서 선언한** 타입도 한정자로 인정한다(중첩·보조 타입)."""
    _java(tmp_path, "a/Outer.java",
          "class Outer { static class Inner { public static final int LIMIT = 7; } }")

    assert CodeValueResolver(tmp_path).resolve("Inner.LIMIT").value == "7"


# ── 값의 출처가 될 수 없는 경로 ────────────────────────────────────────────────

def test_test_sources_are_not_a_value_source(tmp_path):
    """테스트 상수는 제품의 현재값이 아니다.

    실측에서 `EMAIL` 이 테스트의 `"test@example.com"` 으로 잡혔다.
    """
    _java(tmp_path, "app/src/test/java/FixtureA.java",
          'class FixtureA { public static final String EMAIL = "test@example.com"; }')
    _java(tmp_path, "app/src/main/java/Mailer.java",
          'class Mailer { public static final String EMAIL = "noreply@corp"; }')

    r = CodeValueResolver(tmp_path).resolve("EMAIL")
    assert r.found and r.value == '"noreply@corp"'      # 테스트 쪽이 섞였다면 모호로 거절됐다


def test_build_output_is_not_a_value_source(tmp_path):
    """빌드 산출물은 파생물이다 — 거기서 읽으면 '현재값' 이 마지막 빌드 시점의 값이 된다."""
    _java(tmp_path, "app/build/classes/Stale.java",
          "class Stale { public static final int LIMIT = 1; }")
    _java(tmp_path, "app/src/main/java/Live.java",
          "class Live { public static final int LIMIT = 2; }")

    r = CodeValueResolver(tmp_path).resolve("LIMIT")
    assert r.found and r.value == "2"


# ── 배포가 빠졌을 때 조용하지 않다 ──────────────────────────────────────────────

def test_missing_repo_says_so(tmp_path):
    """코드 경로 자체가 없으면 **그렇게 말한다.**

    라이브 배포에서 `/code-src` 가 마운트돼 있지 않았다(2026-08-25). 그 상태에서는 모든 claim 이
    똑같이 not-found 가 되고, 그것은 "claim 이 틀렸다" 와 구분되지 않는다.
    """
    r = CodeValueResolver(tmp_path / "없는경로").resolve("Alpha.LIMIT")
    assert r.found is False
    assert "코드 경로가 없다" in r.reason


# ── 결정론 ────────────────────────────────────────────────────────────────────

def test_resolution_does_not_depend_on_filesystem_order(tmp_path):
    """같은 값이 여러 곳에 있을 때 고르는 파일이 기계마다 달라지면 안 된다.

    옛 판은 `rglob` 이 준 순서를 그대로 썼다 — 그 순서는 OS·파일시스템이 정한다.
    """
    for name in ("zeta/Z.java", "alpha/A.java", "mid/M.java"):
        cls = Path(name).stem
        _java(tmp_path, name, f"class {cls} {{ public static final int LIMIT = 3; }}")

    paths = {CodeValueResolver(tmp_path).resolve("LIMIT").rel_path for _ in range(3)}
    assert paths == {"alpha/A.java"}          # 정렬 결과의 첫 번째, 항상 같다

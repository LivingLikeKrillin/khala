"""해석기가 **어노테이션 인자**를 읽는가 — 그리고 여전히 모호하면 답하지 않는가.

**왜 이 파일이 있나 (2026-08-30 실측).** 해석기는 `static final` 상수만 읽었다. 그래서
문서와 코드를 대 보려던 두 질문(파티 제목 몇 자 · 닉네임 몇 자)에 **아무 답도 못 냈다** —
그 값은 상수가 아니라 `@Size(max = 100)` 과 `@Column(length = 20)` 에 있었다. 상수만 읽는
해석기는 실물 Java 코드베이스에 거의 닿지 못한다.

그리고 이쪽은 모호성이 상수보다 **심하다**. 팀 코드에서 `nickname` 에 걸린 `@Size(max = …)`
가 세 클래스에서 64, 다른 한 클래스에서 20 이었다.
"""

from __future__ import annotations

from pathlib import Path

from nexus.index.code_source import CodeValueResolver


def _java(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


REQUEST = """
package a;
public class CreatePartyroomRequest {
    @NotBlank(message = "Title is required")
    @Size(max = 100, message = "Title must be less than 100 characters")
    private String title;

    @Size(max = 50)
    private String introduction;
}
"""


def test_it_reads_a_validation_annotation(tmp_path):
    """⛔ 이것을 못 읽어서 값 조회가 실물에 닿지 못했다."""
    _java(tmp_path, "a/CreatePartyroomRequest.java", REQUEST)
    r = CodeValueResolver(tmp_path).resolve("CreatePartyroomRequest.title@Size.max")
    assert r.found is True
    assert r.value == "100"
    assert r.rel_path == "a/CreatePartyroomRequest.java"


def test_it_picks_the_right_field_not_the_neighbour(tmp_path):
    """같은 어노테이션이 여러 필드에 붙는다. 위 필드 것을 딸려 오면 값이 뒤바뀐다."""
    _java(tmp_path, "a/CreatePartyroomRequest.java", REQUEST)
    r = CodeValueResolver(tmp_path).resolve("CreatePartyroomRequest.introduction@Size.max")
    assert r.value == "50"


def test_it_picks_the_right_attribute_not_the_first_one(tmp_path):
    """`@Size(max = 100, message = "…")` — `message` 를 집으면 값이 문장이 된다."""
    _java(tmp_path, "a/CreatePartyroomRequest.java", REQUEST)
    r = CodeValueResolver(tmp_path).resolve("CreatePartyroomRequest.title@Size.message")
    assert r.value == '"Title must be less than 100 characters"'


def test_a_paren_inside_a_string_does_not_end_the_arguments(tmp_path):
    """⛔ 실물에 있는 줄이다. `[^)]*` 로 잡으면 `VARCHAR(32)` 의 `)` 에서 끊긴다."""
    _java(tmp_path, "a/AdministratorData.java", """
public class AdministratorData {
    @Column(name = "role", nullable = false, length = 32, columnDefinition = "VARCHAR(32)")
    private String role;
}
""")
    r = CodeValueResolver(tmp_path).resolve("AdministratorData.role@Column.length")
    assert r.found is True
    assert r.value == "32"


def test_an_annotation_on_the_same_line_is_read(tmp_path):
    """실물에 있는 모양 — 어노테이션과 선언이 한 줄에 있다."""
    _java(tmp_path, "a/SystemAnnouncementData.java",
          'public class SystemAnnouncementData { @Column(nullable = false, length = 32) '
          'private AnnouncementType type; }')
    r = CodeValueResolver(tmp_path).resolve("SystemAnnouncementData.type@Column.length")
    assert r.value == "32"


# ── 모호하면 답하지 않는다 ────────────────────────────────────────────────────

def test_the_same_field_with_different_limits_is_refused(tmp_path):
    """⛔ **팀 코드의 실제 모양.** `nickname` 이 클래스마다 다른 한도를 갖는다.

    한정자 없이 아무 값이나 돌려주면 *"닉네임은 64자까지"* 가 확신하는 문장으로 나가는데,
    그 값은 관리자 화면 규칙이고 사용자 화면은 20이다.
    """
    _java(tmp_path, "a/CreateVirtualMemberRequest.java",
          "public class CreateVirtualMemberRequest { @Size(max = 20) private String nickname; }")
    _java(tmp_path, "b/CreateAdministratorRequest.java",
          "public class CreateAdministratorRequest { @Size(max = 64) private String nickname; }")

    r = CodeValueResolver(tmp_path).resolve("nickname@Size.max")
    assert r.found is False
    assert "서로 다른 값" in r.reason


def test_the_qualifier_narrows_it(tmp_path):
    """한정자를 붙이면 갈린다 — 그것이 처방으로 제시되는 이유다."""
    _java(tmp_path, "a/CreateVirtualMemberRequest.java",
          "public class CreateVirtualMemberRequest { @Size(max = 20) private String nickname; }")
    _java(tmp_path, "b/CreateAdministratorRequest.java",
          "public class CreateAdministratorRequest { @Size(max = 64) private String nickname; }")

    r = CodeValueResolver(tmp_path).resolve("CreateVirtualMemberRequest.nickname@Size.max")
    assert r.value == "20"


def test_an_annotation_written_in_a_comment_is_not_code(tmp_path):
    """⛔ 대조군. javadoc 의 예시를 코드로 읽으면 낡은 값이 확신하는 문장으로 나간다."""
    _java(tmp_path, "a/Doc.java", """
public class Doc {
    /** 예전에는 @Size(max = 999) 였다. */
    // @Size(max = 888)
    @Size(max = 30)
    private String title;
}
""")
    r = CodeValueResolver(tmp_path).resolve("Doc.title@Size.max")
    assert r.value == "30"


def test_a_missing_annotation_says_what_is_missing(tmp_path):
    """처방이 갈려야 한다 — claim 을 고칠 일인지 배포를 고칠 일인지."""
    _java(tmp_path, "a/Plain.java", "public class Plain { private String title; }")
    r = CodeValueResolver(tmp_path).resolve("Plain.title@Size.max")
    assert r.found is False
    assert "@Size" in r.reason and "찾지 못했다" in r.reason


def test_a_malformed_source_is_rejected_with_the_shape(tmp_path):
    r = CodeValueResolver(tmp_path).resolve("title@Size")
    assert r.found is False
    assert "클래스.필드@어노테이션.인자" in r.reason


def test_test_sources_are_not_a_source_of_truth(tmp_path):
    """⛔ 대조군. 상수 쪽에서 이미 데인 자리다 — 어노테이션도 같은 규칙이어야 한다."""
    _java(tmp_path, "app/src/test/java/FixtureRequest.java",
          "public class FixtureRequest { @Size(max = 1) private String title; }")
    r = CodeValueResolver(tmp_path).resolve("FixtureRequest.title@Size.max")
    assert r.found is False


def test_constants_still_work(tmp_path):
    """⛔ 대조군. 형태를 하나 더 받느라 원래 형태를 깨면 안 된다."""
    _java(tmp_path, "a/PlanPolicy.java",
          "public class PlanPolicy { public static final int BASIC_MAX_PROJECTS = 3; }")
    r = CodeValueResolver(tmp_path).resolve("PlanPolicy.BASIC_MAX_PROJECTS")
    assert r.found is True and r.value == "3"


# ── 파일을 이미 아는 경우 (`resolve_at`) ──────────────────────────────────────

def test_resolve_at_reads_one_file_without_walking_the_tree(tmp_path):
    """⛔ 요청 경로용. 전체 해석은 이 배포에서 첫 호출이 55.9초이고 그중 50.7초가 목록이다."""
    _java(tmp_path, "a/CreatePartyroomRequest.java", REQUEST)
    # 트리에 잡음을 잔뜩 둬도 결과가 같아야 한다 — 저 파일만 읽기 때문이다.
    for i in range(5):
        _java(tmp_path, f"noise/N{i}.java",
              f"public class N{i} {{ @Size(max = {i}) private String title; }}")

    r = CodeValueResolver(tmp_path).resolve_at("a/CreatePartyroomRequest.java",
                                               "CreatePartyroomRequest.title@Size.max")
    assert r.found is True and r.value == "100"


def test_resolve_at_and_the_full_scan_agree_on_the_hash(tmp_path):
    """드리프트 판정이 두 경로에 걸쳐 성립해야 한다 — 심을 때와 읽을 때가 다른 경로다."""
    _java(tmp_path, "a/CreatePartyroomRequest.java", REQUEST)
    src = "CreatePartyroomRequest.title@Size.max"
    full = CodeValueResolver(tmp_path).resolve(src)
    fast = CodeValueResolver(tmp_path).resolve_at(full.rel_path, src)
    assert fast.symbol_hash == full.symbol_hash


def test_resolve_at_says_the_file_moved_rather_than_guessing(tmp_path):
    r = CodeValueResolver(tmp_path).resolve_at("gone/Nope.java", "Nope.title@Size.max")
    assert r.found is False and "기록된 파일이 없다" in r.reason


def test_resolve_at_says_the_symbol_left_rather_than_falling_back_to_a_scan(tmp_path):
    """⛔ 여기서 전체 훑기로 되돌아가면 요청 하나가 50초를 문다."""
    _java(tmp_path, "a/Req.java", "public class Req { private String title; }")
    _java(tmp_path, "b/Other.java", "public class Other { @Size(max = 9) private String title; }")

    r = CodeValueResolver(tmp_path).resolve_at("a/Req.java", "Req.title@Size.max")
    assert r.found is False and "다시 심어야 한다" in r.reason


def test_resolve_at_works_for_constants_too(tmp_path):
    _java(tmp_path, "a/PlanPolicy.java",
          "public class PlanPolicy { public static final int MAX = 7; }")
    r = CodeValueResolver(tmp_path).resolve_at("a/PlanPolicy.java", "PlanPolicy.MAX")
    assert r.value == "7"


# ── 접근 제어자가 없는 필드 ──────────────────────────────────────────────────

LOMBOK = """
package a;
@Getter
public class UpdateMyBioRequest {
    @Size(max = 20, message = "닉네임은 20자를 초과할 수 없습니다")
    String nickname;

    @Size(max = 50, message = "소개글은 50자를 초과할 수 없습니다")
    String introduction;
}
"""


def test_a_field_without_an_access_modifier_is_still_a_field(tmp_path):
    """⛔ **실물에서 놓친 자리.** Lombok 을 쓰면 제어자를 안 붙인다.

    이것을 못 읽어서 사용자 경로의 닉네임 상한이 안 잡혔고, 나는 관리자·봇 경로만 보고
    *"서버에 길이 검증이 없다"* 고 잘못 보고했다.
    """
    _java(tmp_path, "a/UpdateMyBioRequest.java", LOMBOK)
    r = CodeValueResolver(tmp_path).resolve("UpdateMyBioRequest.nickname@Size.max")
    assert r.found is True and r.value == "20"


def test_the_neighbour_field_is_still_told_apart_without_modifiers(tmp_path):
    _java(tmp_path, "a/UpdateMyBioRequest.java", LOMBOK)
    r = CodeValueResolver(tmp_path).resolve("UpdateMyBioRequest.introduction@Size.max")
    assert r.value == "50"


def test_generic_and_array_types_are_read(tmp_path):
    _java(tmp_path, "a/Holder.java", """
public class Holder {
    @Size(max = 3) List<String> tags;
    @Size(max = 4) String[] names;
}
""")
    res = CodeValueResolver(tmp_path)
    assert res.resolve("Holder.tags@Size.max").value == "3"
    assert res.resolve("Holder.names@Size.max").value == "4"


def test_a_word_in_prose_is_not_a_declaration(tmp_path):
    """⛔ 대조군. 제어자를 안 요구하는 대신 **타입 토큰**을 요구한다 — 없으면 산문이
    선언으로 잡히고, 그러면 이 모듈은 아무 글에서나 값을 읽는다."""
    _java(tmp_path, "a/Doc.java", """
public class Doc {
    @Size(max = 9)
    void method() { int x = 1; }
}
""")
    r = CodeValueResolver(tmp_path).resolve("Doc.x@Size.max")
    assert r.found is False

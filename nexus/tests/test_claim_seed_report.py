"""시드가 **안 붙은 것을 말하는가.**

⛔ **왜 이 파일이 있나 (2026-08-30).** 시드는 `{n}건 적재` 만 찍었고, 이 모듈에는 검사가
하나도 없었다. claim 이 코드에 안 붙는 경우는 흔하다 — 심볼 오타, 한정자 누락, 마운트 빠짐,
값이 애초에 코드에 없음. 그때도 행은 들어간다(값 없이). 그래서 11건을 심고 4건이 조용히
죽어도 화면은 `11건 적재` 였다. **쓰기만 있고 읽기가 없는** 모양이라 이 리포가 반복해서
데인 자리다.
"""

from __future__ import annotations

import pytest
import yaml

from nexus.claims.seed import seed_claims
from nexus.index.code_source import CodeValueResolver


class _Repo:
    """upsert 만 받는 자리. 이 검사는 **보고**를 확인하지 DB 를 확인하지 않는다."""

    def __init__(self):
        self.saved = []

    async def upsert(self, c):
        self.saved.append(c)


def _yaml(tmp_path, items):
    p = tmp_path / "claims.yaml"
    p.write_text(yaml.safe_dump(items, allow_unicode=True), encoding="utf-8")
    return str(p)


def _repo_with(tmp_path, rel, body):
    src = tmp_path / "src"
    f = src / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    return src


def _claim(claim_id, value_source):
    return {"claim_id": claim_id, "kind": "invariant", "concepts": ["개념"],
            "statement": "값이 있다", "value_source": value_source,
            "value_ref_kind": "code_annotation", "criticality": "core",
            "owner": "@owner"}


@pytest.mark.asyncio
async def test_a_claim_that_does_not_bind_is_named_with_its_reason(tmp_path):
    """⛔ 이것이 안 보여서 죽은 claim 이 살아 있는 것처럼 보였다."""
    src = _repo_with(tmp_path, "a/Req.java",
                     "public class Req { @Size(max = 100) private String title; }")
    path = _yaml(tmp_path, [_claim("good", "Req.title@Size.max"),
                            _claim("typo", "Req.titel@Size.max")])

    rep = await seed_claims(path, _Repo(), CodeValueResolver(src))

    assert rep.total == 2
    assert rep.bound == 1
    assert [c for c, _ in rep.unbound] == ["typo"]
    # 이유가 처방을 갈라야 한다 — claim 을 고칠 일이지 배포를 고칠 일이 아니다.
    assert "찾지 못했다" in rep.unbound[0][1]


@pytest.mark.asyncio
async def test_an_unbound_claim_is_still_stored(tmp_path):
    """행은 들어간다 — 값만 없다. 그래서 **보고**가 유일한 신호다."""
    src = _repo_with(tmp_path, "a/Req.java", "public class Req { }")
    path = _yaml(tmp_path, [_claim("nope", "Req.title@Size.max")])

    repo = _Repo()
    rep = await seed_claims(path, repo, CodeValueResolver(src))

    assert len(repo.saved) == 1
    assert repo.saved[0].value_symbol_hash is None
    assert rep.bound == 0


@pytest.mark.asyncio
async def test_a_missing_code_mount_says_so_rather_than_looking_like_a_bad_claim(tmp_path):
    """⛔ 대조군. 마운트가 빠진 배포에서는 **전부** 안 붙는다 — claim 이 틀린 것과 다르다."""
    path = _yaml(tmp_path, [_claim("x", "Req.title@Size.max")])

    rep = await seed_claims(path, _Repo(), CodeValueResolver(tmp_path / "nowhere"))

    assert rep.bound == 0
    assert "코드 경로가 없다" in rep.unbound[0][1]


@pytest.mark.asyncio
async def test_an_ambiguous_source_is_reported_as_ambiguous_not_missing(tmp_path):
    """처방이 다르다 — 한정자를 붙이라는 말이 나와야 한다."""
    src = _repo_with(tmp_path, "a/A.java",
                     "public class A { @Size(max = 20) private String nickname; }")
    (src / "b").mkdir(parents=True, exist_ok=True)
    (src / "b" / "B.java").write_text(
        "public class B { @Size(max = 64) private String nickname; }", encoding="utf-8")
    path = _yaml(tmp_path, [_claim("amb", "nickname@Size.max")])

    rep = await seed_claims(path, _Repo(), CodeValueResolver(src))

    assert "한정자" in rep.unbound[0][1]


@pytest.mark.asyncio
async def test_an_owner_is_still_required(tmp_path):
    """대조군 — 소유권 강제는 그대로여야 한다."""
    item = _claim("x", None)
    item["owner"] = "unknown"
    path = _yaml(tmp_path, [item])

    with pytest.raises(ValueError):
        await seed_claims(path, _Repo(), CodeValueResolver(tmp_path))


@pytest.mark.asyncio
async def test_the_report_still_counts_like_a_number(tmp_path):
    """옛 호출부가 `n` 으로 받아 쓰던 자리를 깨지 않는다."""
    path = _yaml(tmp_path, [_claim("x", None)])
    rep = await seed_claims(path, _Repo(), CodeValueResolver(tmp_path))
    assert int(rep) == 1

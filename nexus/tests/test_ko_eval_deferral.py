"""보류를 사람의 기억이 아니라 스위트가 지키게 한다
(SPEC-nexus-korean-embedding-comparison §4.5, §6).

풀 판정을 보류했다. 보류의 위험은 **다음 사람이 그걸 모르고 gold 를 키우는 것**이다 — 이미 풀에
올라와 있는데 판정만 안 된 문서들이 영원히 비관련으로 남은 채 라벨이 자라면, 그 뒤의 모든 비교가
그 편향을 물려받는다.

그래서 트리거를 문장이 아니라 **테스트**로 둔다: 라벨 리비전이 2를 넘어가는 순간, 커밋된 블라인드
풀이 판정된 흔적이 없으면 실패한다. "누가 기억해서 확인한다"는 트리거는 트리거가 아니다.

하니스 격리도 같은 이유로 여기서 지킨다. `torch`/`sentence-transformers` 는 평가용이고 프로덕션
이미지에 실리면 안 되는데, 그 약속은 SPEC 두 곳에 적혀 있을 뿐 아무것도 검사하지 않았다.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

_NEXUS = Path(__file__).resolve().parents[1]
_LABELS = _NEXUS / "tests" / "eval" / "ko" / "labels.yaml"
_POOL = _NEXUS / "tests" / "eval" / "ko" / "pool-blind.json"
_DEFERRED_AT_REVISION = 2          # 이 리비전에서 판정을 보류했다 (SPEC §4.5)

_HARNESS_ONLY = ("sentence_transformers", "torch")


def _labels() -> dict:
    return yaml.safe_load(_LABELS.read_text(encoding="utf-8"))


# ── 보류 트리거 ──────────────────────────────────────────────────────────────


def test_the_blind_pool_is_committed_for_whoever_resumes():
    """익명 덤프가 없으면 보류가 아니라 그냥 안 한 것이다."""
    assert _POOL.exists(), f"블라인드 풀 덤프가 없다: {_POOL}"
    pool = json.loads(_POOL.read_text(encoding="utf-8"))
    assert pool, "풀이 비었다"
    assert all("candidates" in q for q in pool)
    assert not any(k in q for q in pool for k in ("arm", "model", "source_leg")), (
        "덤프에 실험군 정보가 남아 있다 — 블라인드 판정이 성립하지 않는다")


def test_growing_the_gold_set_requires_judging_the_pool_first():
    """**보류의 트리거.** 라벨이 자라는 순간이 판정하지 않은 대가를 치르는 순간이다.

    리비전이 2를 넘었는데 풀이 그대로면, 이미 풀에 올라온 문서들은 판정 없이 비관련으로 굳는다.
    그 상태로 자란 gold 는 그 뒤 모든 비교에 편향을 물려준다.
    """
    revision = _labels()["revision"]
    if revision <= _DEFERRED_AT_REVISION:
        return
    pool = json.loads(_POOL.read_text(encoding="utf-8"))
    unjudged = sum(len(q["candidates"]) for q in pool)
    assert unjudged == 0, (
        f"라벨이 리비전 {revision} 로 자랐는데 블라인드 풀에 미판정 후보가 {unjudged}건 남아 있다. "
        "gold 를 키우기 전에 이미 풀에 있는 것부터 판정해야 한다 "
        "(SPEC-nexus-korean-embedding-comparison §4.5).")


def test_the_pool_covers_the_answerable_queries():
    pool = {q["id"] for q in json.loads(_POOL.read_text(encoding="utf-8"))}
    answerable = {q["id"] for q in _labels()["queries"] if q["answerable"]}
    assert pool == answerable, "풀이 답변가능 질의 전체를 덮지 않는다"


# ── 하니스 격리 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("module_name", _HARNESS_ONLY)
def test_production_code_never_imports_the_harness_only_libraries(module_name):
    """`nexus/nexus/` 아래 어디에서도 torch·sentence-transformers 를 부르지 않는다."""
    offenders = []
    for f in (_NEXUS / "nexus").rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n.split(".")[0] == module_name for n in names):
                offenders.append(f.relative_to(_NEXUS).as_posix())
    assert offenders == [], f"프로덕션 코드가 {module_name} 을 임포트한다: {offenders}"


def test_the_app_image_dependency_set_excludes_them():
    """이름 검사만으로는 **전이 의존**을 못 잡는다 — 선언된 의존성 목록도 본다.

    프로덕션이 torch 를 얻게 되는 현실적인 경로는 누가 직접 임포트하는 게 아니라, 어떤 패키지가
    그것을 끌고 들어오는 것이다.
    """
    text = (_NEXUS / "pyproject.toml").read_text(encoding="utf-8")
    constraints = (_NEXUS / "constraints.txt")
    haystack = text + (constraints.read_text(encoding="utf-8") if constraints.exists() else "")
    for name in _HARNESS_ONLY:
        assert name not in haystack.replace("-", "_"), (
            f"{name} 이 앱 이미지의 의존성에 들어 있다 — 평가 전용이어야 한다 (SPEC §4.4)")

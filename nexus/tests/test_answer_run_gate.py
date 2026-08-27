"""총점을 언제 내면 안 되는가 — `scripts/ko_eval_answer_run` 의 관문
(SPEC-nexus-answer-quality-ruler §3.2).

**관문이 숫자 뒤에 있으면 숫자를 보고 평가 하니스를 고치게 된다.** 그래서 판단은 총점 출력 이전이고,
막힌 실행도 리포트는 쓴다 — 판정할 재료가 그 리포트 안에 있기 때문이다. 파일이 `partial` 로
막혔다는 사실을 말하고, 사람의 기억이 그 자리를 대신하지 않는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ko_eval_answer_run as run  # noqa: E402
from scripts.ko_eval_answer_quality import aggregate, score_answer  # noqa: E402

TENANT_TITLES = {"정답 문서", "아무도 판정 안 한 문서"}


def _cite(title):
    return {"title": title, "verified": True}


def _summary(*scores):
    return aggregate(list(scores))


def test_a_clean_run_has_nothing_blocking_it():
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    assert run.gate_reasons(_summary(s)) == []


def test_an_unadjudicated_citation_blocks_the_grade():
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    reasons = run.gate_reasons(_summary(s))
    assert reasons and "b" in reasons[0]


def _args(tmp_path):
    """실행 인자 — 리포트 경로가 여기 실려 온다(전역 상수였을 때 회차가 서로를 덮었다)."""
    return SimpleNamespace(tag="t", tenant="default", report=tmp_path / "report.json")


def test_a_blocked_run_still_writes_the_material_it_blocked_on(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    a = _summary(s)
    run._write_report(_args(tmp_path), {"revision": 9}, SimpleNamespace(model="m"),
                      a, [{"qid": "b"}], partial=True)

    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written["partial"] is True
    assert written["summary"]["adjudication_candidates"] == {"b": ["아무도 판정 안 한 문서"]}
    assert written["queries"] == [{"qid": "b"}]


def test_a_complete_run_is_not_marked_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    run._write_report(_args(tmp_path), {"revision": 9}, SimpleNamespace(model="m"),
                      _summary(s), [{"qid": "a"}], partial=False)
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["partial"] is False


def test_an_expired_label_blocks_the_grade_too():
    """만료된 라벨은 사라진 텍스트에 대한 주장이다 — 그 위에서 나온 총점은 결과가 아니다."""
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    reasons = run.gate_reasons(_summary(s), ["pb-part-01", "pb-space-05"])
    assert reasons and "만료된 라벨 2건" in reasons[0]


def test_the_two_reasons_are_reported_separately():
    s = score_answer("b", "100 곡 [출처: 아무도 판정 안 한 문서]",
                     [_cite("아무도 판정 안 한 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT_TITLES)
    assert len(run.gate_reasons(_summary(s), ["pb-part-01"])) == 2


# ── 실행별 산출물 경로 ────────────────────────────────────────────────────────
#
# 리포트가 고정 경로 하나였을 때, 충분성 런의 격자(파라메트릭 2건이 **어느 질의였는지**)가 40초
# 뒤 다음 런에 덮여 복구 불가능해졌다. 누적 로그는 요약과 `ok` 맵만 담아 되살릴 수도 없었다.

def test_the_report_path_carries_the_tag_and_the_run_log_does_not():
    """리포트는 회차마다 갈라져야 하고, 누적 로그는 **한 파일이어야** 잡음 폭이 읽힌다."""
    r1, runs1 = run.resolve_paths(run.DEFAULT_LABELS, "rev6-r1")
    r2, runs2 = run.resolve_paths(run.DEFAULT_LABELS, "rev6-r2")
    assert r1 != r2, "두 회차가 같은 파일에 쓰면 앞 회차의 판정 재료가 사라진다"
    assert runs1 == runs2, "회차 간 변동은 한 파일에 모여야 폭이 된다"
    assert "rev6-r1" in r1.name and "rev6-r1" not in runs1.name


def _write_labels(path, pack="packa-corpus-266"):
    """경로 계산에 필요한 최소 라벨 — `pack` 이 산출물 이름을 정한다."""
    path.write_text(f"pack: {pack}\nqueries: []\n", encoding="utf-8")
    return path


def test_a_different_label_set_writes_to_different_files(tmp_path):
    """라벨셋이 다르면 산출물이 자동으로 갈라진다 — 두 코퍼스의 수가 한 파일에서 섞이면 안 된다."""
    other = tmp_path / "answer-labels.yaml"
    _write_labels(other)

    b_report, b_runs = run.resolve_paths(run.DEFAULT_LABELS, "r1")
    a_report, a_runs = run.resolve_paths(other, "r1")
    assert b_report.name.startswith("packb-") and a_report.name.startswith("packa-")
    assert b_runs != a_runs


def test_the_prefix_comes_from_the_pack_not_the_file_name(tmp_path):
    """파일 이름은 사람이 붙이고 팩 이름은 라벨이 선언한다.

    이름에서 따던 첫 판은 Pack A 의 `answer-labels.yaml` 에서 `answer-answer-runs.jsonl` 을
    만들었다 — 실제로 그렇게 찍혔다.
    """
    lp = tmp_path / "answer-labels.yaml"
    _write_labels(lp)
    report, runs = run.resolve_paths(lp, "r1")
    assert runs.name == "packa-answer-runs.jsonl"
    assert "answer-answer" not in report.name


def test_results_live_beside_their_labels(tmp_path):
    """공개 라벨의 결과만 gitignore 안으로 가면 앞뒤가 안 맞는다 — 결과는 자기 라벨 옆에 산다."""
    lp = tmp_path / "answer-labels.yaml"
    _write_labels(lp)
    report, runs = run.resolve_paths(lp, "r1")
    assert report.parent == tmp_path and runs.parent == tmp_path


def test_a_missing_labels_file_does_not_crash_path_resolution(tmp_path):
    """경로 계산이 먼저 죽으면 진짜 원인("라벨 파일이 없다")이 스택 아래로 숨는다."""
    report, _ = run.resolve_paths(tmp_path / "packb-labels.yaml", "r1")
    assert report.name.startswith("packb-")


def test_an_untagged_run_still_has_a_path():
    report, _ = run.resolve_paths(run.DEFAULT_LABELS, "")
    assert report.name == "packb-answer-quality.json"


# ── 등급으로 못 읽는 gold (2026-08-12) ───────────────────────────────────────
#
# q002 가 4런 연속 실패했고 원인은 랭킹이 아니었다: gold 인 `tutorials/security/apparmor.md` 가
# 경로 규칙(`**/security/**`)으로 RESTRICTED 인데 실행은 INTERNAL 로 돌아, 검색의
# `classification <= clearance` 가 그 문서를 원천 배제했다. **정책 준수를 검색 실패로 적었다.**

class _Con:
    """`unreadable_gold` 가 쓰는 것은 `fetch` 하나다."""

    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *_a):
        return [{"key": k, "classification": c} for k, c in self._rows]


_DOCS = [("public.md", "PUBLIC"), ("normal.md", "INTERNAL"), ("secret.md", "RESTRICTED")]


def _labels(*golds):
    return {"queries": [{"id": f"q{i}", "answerable": True, "gold": list(g)}
                        for i, g in enumerate(golds, 1)]}


async def test_gold_above_the_clearance_is_named():
    blind = await run.unreadable_gold(_Con(_DOCS), _labels(["secret.md"]), "t", "INTERNAL")
    assert "q1" in blind and "RESTRICTED" in blind["q1"][0]


async def test_a_query_whose_every_gold_is_unreadable_is_impossible():
    """전부 못 읽으면 어떤 질의문으로도 통과할 수 없다 — 총점에 섞이면 안 된다."""
    blind = await run.unreadable_gold(_Con(_DOCS), _labels(["secret.md"]), "t", "INTERNAL")
    assert "**통과 불가능**" in blind["q1"]


async def test_a_query_with_one_readable_gold_is_flagged_but_not_impossible():
    """남은 gold 로 통과할 수 있다 — 막을 것은 숫자를 거짓으로 만드는 것뿐이다."""
    blind = await run.unreadable_gold(
        _Con(_DOCS), _labels(["secret.md", "normal.md"]), "t", "INTERNAL")
    assert "**통과 불가능**" not in blind["q1"]


async def test_nothing_is_flagged_when_the_clearance_covers_the_corpus():
    assert await run.unreadable_gold(
        _Con(_DOCS), _labels(["secret.md"]), "t", "RESTRICTED") == {}


async def test_a_lower_clearance_flags_more():
    """등급은 측정하는 조건이다 — 낮추면 더 많은 gold 가 사라진다."""
    blind = await run.unreadable_gold(_Con(_DOCS), _labels(["normal.md"]), "t", "PUBLIC")
    assert "q1" in blind


async def test_an_unknown_clearance_is_refused_not_guessed():
    """모르는 등급을 통과시키면 필터와 게이트가 다른 순서를 믿게 된다."""
    import pytest

    with pytest.raises(ValueError):
        await run.unreadable_gold(_Con(_DOCS), _labels(["normal.md"]), "t", "SECRET-ISH")


async def test_the_gate_speaks_the_databases_vocabulary():
    """등급 이름은 정본(`nexus.auth.clearance`) 하나에서만 온다.

    이 파일의 게이트는 한때 자기 사본(`_LEVELS`)을 들고 있었고 거기엔 `CONFIDENTIAL` 이 있었다.
    Postgres enum 은 `PUBLIC < INTERNAL < RESTRICTED` 셋뿐이라, 그 이름으로 `--clearance` 를
    주면 **게이트는 통과시키고 SQL 캐스트가 터진다**. 정본을 지키는 parity 테스트는 이미
    있었지만(`test_sql_enum_parity`), 사본은 그 회귀 검사 밖에 있었다.
    """
    import pytest

    from nexus.auth import clearance

    for level in clearance.LEVELS:                    # 아는 등급은 전부 받는다
        await run.unreadable_gold(_Con(_DOCS), _labels(["public.md"]), "t", level)

    for unknown in ("CONFIDENTIAL", "SECRET", "internal "):   # DB 에 없는 이름은 거부
        with pytest.raises(ValueError):
            await run.unreadable_gold(_Con(_DOCS), _labels(["public.md"]), "t", unknown)


# ── 실행 조건이 리포트에 남는가 (2026-08-17) ─────────────────────────────────
#
# r3·r4 와 r5 를 정면 비교할 수 없었다. 리포트에 **등급이 없어서** 옛 실행이 어떤 clearance 로
# 돌았는지 알 수 없었고, 같은 날 프롬프트도 바뀌었는데 그 경계도 파일 밖이었다. 모델 이름만
# 남기면 "지난주보다 좋아졌다" 가 검증 불가능한 말이 된다.


def _args_full(tmp_path):
    return SimpleNamespace(tag="t", tenant="default", report=tmp_path / "report.json",
                           clearance="RESTRICTED", limit=40,
                           labels=Path("answer-labels.yaml"), runs=tmp_path / "runs.jsonl")


def test_the_report_records_the_clearance_it_ran_with(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_DIR", tmp_path)
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    run._write_report(_args_full(tmp_path), {"revision": 9}, SimpleNamespace(model="m"),
                      _summary(s), [{"qid": "a"}], partial=False)

    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written["clearance"] == "RESTRICTED"
    assert written["limit"] == 40
    assert len(written["answer_prompt_sha"]) >= 8      # 프롬프트 텍스트에서 파생된 지문


def test_the_prompt_fingerprint_follows_the_prompt(tmp_path, monkeypatch):
    """지문이 프롬프트를 실제로 따라가는지 — 상수를 적어 둔 것이면 이 검사가 잡는다."""
    from nexus.llm import prompts

    before = run.run_conditions(_args_full(tmp_path))["answer_prompt_sha"]
    monkeypatch.setattr(prompts, "SYSTEM_PROMPT", prompts.SYSTEM_PROMPT + "\n8. 새 규칙")
    assert run.run_conditions(_args_full(tmp_path))["answer_prompt_sha"] != before


def test_the_accumulated_log_carries_the_same_conditions(tmp_path):
    """누적 로그가 조건을 빼면, 잡음 폭을 측정하는 그 파일만으로는 회차를 구별할 수 없다."""
    s = score_answer("a", "100 곡 [출처: 정답 문서]", [_cite("정답 문서")], {"정답 문서"},
                     [["100"]], known_titles=TENANT_TITLES)
    args = _args_full(tmp_path)
    run.append_run(args, SimpleNamespace(model="m"), _summary(s), [s], {})

    row = json.loads((tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["clearance"] == "RESTRICTED"
    assert row["answer_prompt_sha"]

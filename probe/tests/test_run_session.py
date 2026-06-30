"""run_mutation 오케스트레이션 seam 단위 테스트(cosmic-ray 없이, runner 주입).

M-2 회귀: 고정 세션 파일명(probe.sqlite/.cfg.toml)이 다중 모듈 루프에서 충돌하고
소비자 작업트리에 잔여물을 남기던 문제를 고정 — 호출별 고유 세션 + 자동 정리.
"""

from khala.probe.run import run_mutation


def _recording_runner(seen, dump_text=""):
    """cosmic-ray 호출을 기록하고 dump엔 고정 텍스트를 돌려주는 가짜 runner."""
    def runner(args, workdir):
        seen.append(list(args))
        return dump_text if args[0] == "dump" else ""
    return runner


def test_run_mutation_uses_unique_session_per_call(tmp_path):
    seen = []
    runner = _recording_runner(seen)
    run_mutation("a.py", tmp_path, runner=runner)
    run_mutation("b.py", tmp_path, runner=runner)
    init_sessions = [args[-1] for args in seen if args[0] == "init"]
    assert len(init_sessions) == 2
    assert len(set(init_sessions)) == 2  # 두 호출이 서로 다른 세션 경로 — 충돌 없음


def test_run_mutation_leaves_no_litter_in_workdir(tmp_path):
    run_mutation("a.py", tmp_path, runner=_recording_runner([]))
    assert list(tmp_path.iterdir()) == []  # 작업트리에 config/session 잔여물 0


def test_run_mutation_extracts_survivors_from_dump(tmp_path, fixtures_dir):
    dump_text = (fixtures_dir / "cr_dump_sample.jsonl").read_text(encoding="utf-8")
    survivors = run_mutation(
        "src/khala/arbiter/review.py", tmp_path,
        runner=_recording_runner([], dump_text=dump_text),
    )
    assert len(survivors) == 1  # 샘플 픽스처는 survivor 1건

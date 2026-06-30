import shutil
import textwrap

import pytest

from khala.probe.run import run_mutation

pytestmark = pytest.mark.skipif(
    shutil.which("cosmic-ray") is None, reason="cosmic-ray 미설치"
)


def test_run_surfaces_known_survivor(tmp_path):
    """행위검증 없는 모듈 → 변이가 살아남아야 한다."""
    (tmp_path / "m.py").write_text("def f(x):\n    return x > 0\n", encoding="utf-8")
    # 반환값을 검증하지 않는 테스트 = 약한 테스트 → 변이 생존 유발
    # (이 test 파일 디렉토리가 pytest rootdir에 들어가 `import m`이 동작)
    (tmp_path / "test_m.py").write_text(
        textwrap.dedent(
            """
            from m import f
            def test_f_runs():
                f(1)   # 단언 없음 — 의도적 약한 테스트
            """
        ),
        encoding="utf-8",
    )
    survivors = run_mutation(module_path="m.py", workdir=tmp_path)
    assert len(survivors) >= 1

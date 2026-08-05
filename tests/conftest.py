"""루트 e2e 는 **두 도구가 한 환경에 있어야** 돈다 — 그리고 그게 조용히 안 되는 것이 문제였다.

`tests/` 의 두 스위트는 Arbiter 와 Nexus 를 A2A 로 실제로 연결해 돌리는 유일한 검사다. 각
스위트는 `pytest.importorskip` 으로 시작하므로, 한쪽만 설치된 환경에서는 **스킵**된다. 어떤 CI
잡도 두 패키지를 함께 설치하지 않았기 때문에 이 스위트는 머지 이후 한 번도 CI 에서 돈 적이 없다
— 통과한 것이 아니라 **없는 검사**였다(같은 교훈: `NEXUS_REQUIRE_MECAB`).

그래서 CI 는 `KHALA_REQUIRE_E2E=1` 로 돈다. 그 값이 켜져 있으면 임포트 실패가 스킵이 아니라
**수집 실패**가 된다. 로컬에서는 켜지 않아도 되고, 그때는 예전처럼 조용히 스킵된다.
"""

from __future__ import annotations

import importlib
import os

import pytest

#: 이 스위트가 실제로 무엇을 필요로 하는가. `nexus[mcp]` 는 **일부러 빠져 있다** — arbiter 가
#: `mcp>=2` 를, nexus 의 mcp 확장이 `mcp<2` 를 요구해서 한 환경에 같이 못 산다. e2e 가 만지는
#: nexus 코어는 mcp 를 임포트하지 않으므로 그 확장 없이 둘을 공존시킨다.
REQUIRED = ("nexus", "khala.arbiter", "a2a.compat.v0_3.types")


def pytest_configure(config: pytest.Config) -> None:
    if os.getenv("KHALA_REQUIRE_E2E") != "1":
        return
    missing = []
    for module in REQUIRED:
        try:
            importlib.import_module(module)
        except Exception as e:      # noqa: BLE001 — 무엇이 없는지가 메시지의 내용이다
            missing.append(f"{module} ({type(e).__name__}: {e})")
    if missing:
        raise pytest.UsageError(
            "KHALA_REQUIRE_E2E=1 인데 교차도구 e2e 의 전제가 없다: " + " · ".join(missing)
            + "\nnexus 는 `.[dev,a2a]` 로(mcp 확장 없이), arbiter 는 `.[dev]` 로 설치한다.")

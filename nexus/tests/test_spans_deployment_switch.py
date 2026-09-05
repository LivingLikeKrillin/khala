"""배포 설정이 **단계 span 캡처를 켜 두고 있는가** (SPEC-nexus-stage-spans, Unit 1).

Unit 1 은 `spans.enabled: false` 인 채로 머지됐다(#440) — 스키마·제약·파괴 경로를 행이
하나도 없는 동안 CI 에서 먼저 검증하기 위해서다. 2026-09-05 소유자가 켰다.

⛔ **왜 이 검사가 있나.** 코드 기본값은 꺼짐이고(`hybrid.py`: `spans_cfg.get("enabled")`),
켜는 것은 `config.yaml` 한 줄이다. 그 줄이 사라지거나 `"false"` 같은 따옴표 하나로 뒤집혀도
**단위 검사는 전부 초록이다** — span 을 쓰는 테스트들은 전부 자기 cfg 를 직접 넘기기 때문에
배포 설정을 한 줄도 읽지 않는다. 이 리포가 반복해서 데인 모양이고(`test_deployment_search_
switches.py` 머리말), 이번에는 켜기 전에 등록해 둔다.

**끄는 것을 막는 검사가 아니다.** 캡처는 질의 지문을 쌓으므로 끌 이유가 생길 수 있다.
끄기로 결정했다면 이 파일도 같이 고치면 되고, 그때 **결정이 커밋에 남는다**.

⚠ **이 검사가 단언하지 못하는 것.** 요청 경로의 `nexus.api._load_config()` 는 `config.yaml`
을 **프로세스 cwd 기준**으로 읽는다. 그래서 "리포의 파일이 true 다" 와 "돌고 있는 배포가
true 를 본다" 는 서로 다른 주장이고, 여기서 다는 것은 앞의 것뿐이다. 뒤의 것은 켠 뒤
`search_span` 에 행이 실제로 쌓이는지로만 확인된다.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


def _spans_config() -> dict:
    return (yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}).get("spans", {}) or {}


def test_the_deployment_config_has_span_capture_on():
    cfg = _spans_config()
    assert cfg.get("enabled") is True, (
        "배포 설정에서 span 캡처가 꺼졌다 — 켜져 있어야 단계별 진단 자료가 쌓인다. "
        "끄기로 결정했다면 이 검사도 같이 고쳐라(그러면 결정이 커밋에 남는다)."
    )


def test_enabled_is_a_boolean_not_a_string():
    """⛔ YAML 에서 `"false"` 는 참이고 `"true"` 도 참이다 — 따옴표 하나가 스위치를 무의미하게 만든다."""
    cfg = _spans_config()
    assert isinstance(cfg.get("enabled"), bool), f"enabled 가 불리언이 아니다: {cfg.get('enabled')!r}"


def test_a_retention_window_is_set_because_it_is_the_only_thing_bounding_the_risk():
    """후보 행은 질의의 지문이다. 그 위험을 묶는 것은 보존 창 하나뿐이라 켠 채로 비워 두면 안 된다."""
    days = _spans_config().get("candidate_retain_days")
    assert isinstance(days, int) and not isinstance(days, bool) and days > 0, (
        f"candidate_retain_days 가 양의 정수가 아니다: {days!r} — "
        "캡처가 켜진 채 보존 창이 없으면 지워지지 않는다."
    )


def test_the_per_span_cap_is_set_so_one_request_cannot_write_without_bound():
    cap = _spans_config().get("max_candidates_per_span")
    assert isinstance(cap, int) and not isinstance(cap, bool) and cap > 0, (
        f"max_candidates_per_span 이 양의 정수가 아니다: {cap!r}"
    )

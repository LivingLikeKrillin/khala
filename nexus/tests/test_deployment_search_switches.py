"""배포 설정이 **답변 보강 장치들을 켜 두고 있는가.**

⛔ **왜 이 검사가 있나.** 정정 확인 패스(#340)와 짝 확장(#342)은 코드 기본값이 꺼짐이고,
켜는 것은 `config.yaml` 한 줄이다. 그 줄이 사라지거나 오타가 나면 **둘 다 조용히 꺼지고
단위 검사는 전부 초록**이다 — 이 리포가 반복해서 데인 모양이다(등록이 `__main__` 뒤에
있던 것 · 사본이 정본 그물 밖이던 것 · 하니스가 프로덕션 경로를 안 타던 것).

**끄는 것을 막는 검사가 아니다.** 끄기로 결정했다면 이 검사도 같이 고치면 된다 —
그때 **결정이 커밋에 남는다**는 것이 이 검사의 값이다. 지금은 측정으로 켠 상태다:

    정정 확인 패스   처치 라벨 0/5 → 5/5, 대조군 무해
    짝 확장         처치 라벨 0/5 → 4/5, 대조군 무해
    절 채움         다중홉 요구 커버리지 7/8 → 8/8
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"

#: 켜져 있어야 하는 스위치와, 그것이 없으면 무엇을 잃는가.
SWITCHES = {
    "reconcile_pass": "정정당한 문서가 정정한 문서를 이긴다 (옛 값이 현행으로 답해진다)",
    "pair_expansion": "설계와 구현 계획이 갈려 두 문서를 함께 봐야 하는 질문이 반쪽이 된다",
    "section_fill": "히트가 앉은 절의 나머지가 근거에서 빠진다",
}


def _search_config() -> dict:
    return (yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}).get("search", {}) or {}


def test_the_deployment_config_keeps_the_answer_switches_on():
    cfg = _search_config()
    off = {k: why for k, why in SWITCHES.items() if cfg.get(k) is not True}
    assert not off, "배포 설정에서 꺼졌다 — " + " · ".join(f"{k}: {why}" for k, why in off.items())


def test_each_switch_is_a_boolean_not_a_string():
    """⛔ `"false"` 는 참이다. YAML 에서 따옴표 하나가 스위치를 조용히 뒤집는다."""
    cfg = _search_config()
    for k in SWITCHES:
        assert isinstance(cfg.get(k), bool), f"{k} 가 불리언이 아니다: {cfg.get(k)!r}"

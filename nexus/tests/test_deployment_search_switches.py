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
    # **2026-09-07 추가 (`OPEN.md` A94).** 앞의 셋과 **모양이 같다**: 코드 기본값 꺼짐 ·
    # `config.yaml` 한 줄로 켜짐 · 그 줄이 사라져도 단위 검사는 전부 초록. 위 docstring 이
    # 적은 이 검사의 존재 이유(*끄는 것을 막는 게 아니라 **결정이 커밋에 남게** 하는 것*)가
    # 그대로 걸린다.
    #
    # ⛔ **이유가 아닌 것 하나를 적어 둔다.** 이 항목은 내가 공개 문서에 *"빠진 넷 중 셋이 이
    # 검사에 못 박혀 있다"* 고 **틀리게 적은 것**(실제로는 둘)을 고치다 나왔다. 그때 넣지
    # 않은 것은 **틀린 문장을 참으로 만들려고 세상을 고치는 것**이 되기 때문이고, 문장은
    # 따로 정정했다. 지금 넣는 근거는 그 문장이 아니라 **위 세 줄과 같은 실패 모양**이다.
    # 가늠자는 하나였다 — *그 문장이 애초에 없었어도 넣었을까?* 넣었을 것이다.
    "code_values": "문서의 값 옆에 코드의 현재 값이 안 선다 (갈린 자리를 사람이 못 본다)",
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

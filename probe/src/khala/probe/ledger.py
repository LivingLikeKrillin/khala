import datetime
from dataclasses import dataclass

import yaml

from khala.probe.models import Survivor, Verdict

_PERMANENT = {"equivalent", "low-value"}


@dataclass(frozen=True)
class Ledger:
    """영속 판정 기록. key(`module:lineno:operator`) -> waiver 매핑."""

    waivers: dict[str, dict]


def load_ledger(text: str) -> Ledger:
    """probe-ledger.yaml 텍스트 -> Ledger. 빈/없는 내용은 빈 원장."""
    data = yaml.safe_load(text) or {}
    waivers = {w["key"]: w for w in (data.get("waivers") or [])}
    return Ledger(waivers=waivers)


def new_survivors(survivors: list[Survivor], ledger: Ledger) -> list[Survivor]:
    """원장에 아직 기록되지 않은 survivor만(= Critic 재심의 대상)."""
    return [s for s in survivors if s.key not in ledger.waivers]


def is_silenced(waiver: dict, today: datetime.date) -> bool:
    """이 waiver가 리포트/게이트에서 침묵되는가.

    equivalent/low-value는 영구 침묵. real-gap은 명시적 `waived_until`이 아직
    만료되지 않았을 때만 침묵 — 만료/부재 시 다시 부상(spec §5).
    """
    if waiver["verdict"] in _PERMANENT:
        return True
    waived_until = waiver.get("waived_until")
    if waived_until is None:
        return False
    return today <= waived_until


def dump_ledger(ledger: Ledger) -> str:
    """Ledger -> probe-ledger.yaml 텍스트(커밋되는 영속 형식, spec §5)."""
    waivers = list(ledger.waivers.values())
    return yaml.safe_dump({"waivers": waivers}, sort_keys=False, allow_unicode=True)


def biting(survivors: list[Survivor], ledger: Ledger, today: datetime.date) -> list[Survivor]:
    """현재 무는(=리포트 headline·M3 게이트가 막을) survivor: 원장에 real-gap으로
    기록됐고 침묵되지 않은 것. 원장에 없는(미triage) survivor는 제외(아직 판정 전)."""
    out = []
    for s in survivors:
        waiver = ledger.waivers.get(s.key)
        if waiver is None:
            continue
        if waiver["verdict"] == "real-gap" and not is_silenced(waiver, today):
            out.append(s)
    return out


def absorb(ledger: Ledger, verdicts: list[Verdict], today: datetime.date) -> Ledger:
    """verdict들을 원장에 새 waiver로 기록한 새 Ledger 반환(입력 불변).

    기존 항목(사람이 손으로 단 `waived_until` 등)은 보존한다.
    """
    waivers = dict(ledger.waivers)
    for v in verdicts:
        waivers[v.survivor_key] = {
            "key": v.survivor_key,
            "verdict": v.verdict,
            "rationale": v.rationale,
            "recorded": today,
        }
    return Ledger(waivers=waivers)

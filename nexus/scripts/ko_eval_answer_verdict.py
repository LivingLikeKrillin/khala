"""답변 품질 실험군 비교의 판정 규칙 — **숫자를 보기 전에 고정한다.**

Pack A·B 의 토크나이저·임베딩 비교는 검색이었고 검색은 결정론이다: 같은 코퍼스에 같은 질의를
넣으면 같은 순위가 나온다(그것을 보장하려고 전순서 정렬 키를 넣었다). **답변은 아니다.** 같은
입력·같은 프롬프트로 세 번 돌렸더니 흔들렸다:

    17:19  grounded 24 · 셋 다 22 · 인용 0개 5
    17:29  grounded 25 · 셋 다 22 · 인용 0개 3      ← 검증기 동일, 순수 잡음
    17:51  grounded 34 · 셋 다 31 · 인용 0개 4      ← 검증기 수정 후

앞 두 줄이 같은 조건이고 `인용 0개` 가 5→3 으로 움직였다. 그러니 **한 번 돌린 두 숫자를 비교하면
모델이 아니라 잡음을 비교하게 된다.** 규칙이 그것을 다뤄야 한다.

## 규칙 (2026-08-08, 어떤 실험군도 돌리기 전에 기록)

1. **팔당 3회 반복.** 질의별 결과는 3회 중 **2회 이상 `ok`** 면 `ok` — 다수결로 회차 잡음을
   한 번 접는다.
2. **잡음 폭을 먼저 보고한다.** 같은 실험군 3회의 `all_three` 최대−최소가 잡음 폭이다. 두 실험군의
   다수결 `all_three` 차이가 **그 폭 이하이면 검정을 돌리지 않고** "회차 변동과 구별되지 않음" 을
   결론으로 적는다. 검정을 먼저 돌려 p 를 보고 나서 이 문장을 쓰면 사후 선택이 된다.
3. 폭을 넘으면 **질의별 다수결 결과에 양측 정확 이항검정**(부호검정), α = 0.05.
4. **불일치쌍 6 미만이면 p 값을 내지 않고 "검정력 부족"** — Pack A·B 와 같은 `MIN_DISCORDANT`.
5. 결론 못 내면 **현직 유지.** 측정 안 된 이득에 비용을 내지 않는다.

층별 수치는 **서술용**이다. 8건짜리 층은 아무것도 결정하지 못한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.ko_eval_harness import MIN_DISCORDANT, sign_test_p

#: 팔당 반복 횟수. 다수결이 뜻을 가지려면 홀수여야 한다.
REPEATS = 3


@dataclass(frozen=True)
class ArmSummary:
    """한 실험군의 반복 실행 묶음."""
    tag: str
    per_query: dict[str, list[bool]]        # 질의 → 회차별 ok

    @property
    def runs(self) -> int:
        return max((len(v) for v in self.per_query.values()), default=0)

    def majority(self) -> dict[str, bool]:
        """질의별 다수결. 회차 잡음을 한 번 접는다."""
        return {q: sum(v) * 2 > len(v) for q, v in self.per_query.items()}

    def totals(self) -> list[int]:
        """회차별 `all_three` 합계 — 잡음 폭은 여기서 나온다."""
        n = self.runs
        return [sum(1 for v in self.per_query.values() if i < len(v) and v[i]) for i in range(n)]

    @property
    def noise_band(self) -> int:
        t = self.totals()
        return (max(t) - min(t)) if t else 0


def compare(champion: ArmSummary, challenger: ArmSummary) -> dict:
    """두 실험군. **규칙 2 가 규칙 3 보다 먼저 걸린다** — 폭 안이면 검정을 아예 안 돌린다."""
    cm, hm = champion.majority(), challenger.majority()
    shared = sorted(set(cm) & set(hm))
    c_total = sum(1 for q in shared if cm[q])
    h_total = sum(1 for q in shared if hm[q])
    band = max(champion.noise_band, challenger.noise_band)
    out = {
        "queries": len(shared),
        "champion": {"tag": champion.tag, "majority_ok": c_total, "runs": champion.totals()},
        "challenger": {"tag": challenger.tag, "majority_ok": h_total, "runs": challenger.totals()},
        "noise_band": band,
        "difference": h_total - c_total,
    }
    if abs(h_total - c_total) <= band:
        out["decision"] = (f"차이 {h_total - c_total:+d} 가 회차 변동 폭 ±{band} 이하 — "
                           f"구별되지 않는다. 현직({champion.tag}) 유지")
        return out

    wins = sum(1 for q in shared if hm[q] and not cm[q])
    losses = sum(1 for q in shared if cm[q] and not hm[q])
    out["wins"], out["losses"], out["ties"] = wins, losses, len(shared) - wins - losses
    if wins + losses < MIN_DISCORDANT:
        out["decision"] = (f"불일치쌍 {wins + losses} < {MIN_DISCORDANT} — 검정력 부족. "
                           f"차이 없음이 아니라 **검정이 결론을 낼 수 없다**. 현직 유지")
        return out
    p = sign_test_p(wins, losses)
    out["p"] = p
    out["decision"] = (f"{wins}승 {losses}패 · p={p:.3f} → "
                       + (f"{challenger.tag} 우세" if p <= 0.05 and wins > losses else
                          f"{champion.tag} 우세" if p <= 0.05 else
                          f"측정 가능한 차이 없음 — 현직({champion.tag}) 유지"))
    return out

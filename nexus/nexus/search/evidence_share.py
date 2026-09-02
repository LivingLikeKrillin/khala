"""근거가 **어느 코퍼스에서 왔는가** — 질문 하나당 테넌트별 조각 수.

**왜 있나 (SPEC-nexus-design-corpus-cutover §5.3).** 읽기 범위가 목록이 된 뒤로 한 답변의
근거는 여러 테넌트에서 온다. 그런데 기록에는 그것을 말하는 칸이 없었다:

| 칸 | 무엇을 말하나 | 무엇을 못 말하나 |
|---|---|---|
| `search_log.tenant` | 누구에게 **귀속**되는가(단일 값) | 근거가 어디서 왔는가 |
| `search_log.read_scope` | 무엇을 **읽을 수 있었는가** | 실제로 무엇을 읽었는가 |

⛔ 그래서 **범위를 넓혀 놓고 근거가 한쪽에서만 오는 상태**와 고르게 오는 상태가 기록에서
똑같아 보인다. 컷오버가 값을 냈는지 안 냈는지를 그 두 칸으로는 못 가른다.

**비율이 아니라 개수를 남긴다.** 비율은 분모를 지운다 — `1.00` 이 조각 하나인지 스무 개인지
같아 보인다. 개수를 남기면 비율은 언제든 나오고 그 반대는 안 된다.

⛔ **문턱을 두지 않는다.** §5.3 이 *"첫 회차는 관측이고 임계는 그 분포를 보고 정한다"* 고
적어 둔 그대로다. 그리고 이 리포는 측정해 본 적 없는 수로 문을 만드는 실수를 이미 했다
(OPEN.md D2 · `persistence-health` 의 같은 판단).
"""

from __future__ import annotations

#: 조각에 테넌트가 안 실려 온 경우의 이름. **버리지 않는다** — 버리면 분모가 조용히 줄고,
#: 그러면 이 값이 말하려던 비율이 틀린다. 이 이름이 보이면 `SearchHit` 을 만드는 자리 중
#: 하나가 테넌트를 안 싣고 있다는 뜻이다.
UNKNOWN = "(미상)"

_PAIR = ":"
_SEP = ","

#: 이보다 적은 질문에서는 **비율을 내지 않는다.** 개수는 그대로 낸다.
#:
#: ⛔ 이것은 문턱이 아니라 **읽기 규율**이다. 첫 행 하나로 `100.0%` 를 찍어 봤더니 그 수가
#: 인용될 만해 보였다 — 질문 하나짜리 비율인데. 같은 규율을 이 리포가 이미 한 번 정했다
#: (D5: 표본 10건 전에는 비율을 내지 않는다).
MIN_SAMPLE = 10


def counts(items) -> list[tuple[str, int]]:
    """`(테넌트, 조각 수)` — **많은 것부터, 같으면 이름 순.**

    `items` 는 `.tenant` 를 가진 것이면 무엇이든 된다 — `SearchHit` 이든
    `EvidenceSnippet` 이든. 답변 경로는 패킷을, 검색 경로는 히트를 넘긴다.
    """
    tally: dict[str, int] = {}
    for it in items or ():
        name = (getattr(it, "tenant", "") or "").strip() or UNKNOWN
        tally[name] = tally.get(name, 0) + 1
    return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))


def encode(items) -> str | None:
    """`design_docs:6,default:4`. 근거가 없으면 `None`.

    ⛔ **TEXT 칸에 들어갈 수 있는 모양만 낸다** (실측 2026-09-02). 목록을 `str` 칸에 그대로
    넣었다가 적재가 34시간 조용히 죽었다 — 직렬화는 이 함수 하나에서만 일어난다.

    ⚠ `None` 은 **근거 조각이 하나도 없었다** 이거나 **이 칸이 생기기 전의 행**이다. 둘은
    `search_log.n_snippets` 와 `ts` 로 갈린다. 두 뜻이 한 칸에 있는 것을 여기 적어 둔다 —
    적어 두지 않으면 다음 사람이 하나로 읽는다.
    """
    pairs = counts(items)
    if not pairs:
        return None
    return _SEP.join(f"{name}{_PAIR}{n}" for name, n in pairs)


def decode(text: str | None) -> list[tuple[str, int]]:
    """`encode` 의 역. **같은 파일에 둔다** — 읽는 쪽이 형식을 따로 알면 그 순간 사본이다."""
    out: list[tuple[str, int]] = []
    for part in (text or "").split(_SEP):
        name, sep, num = part.rpartition(_PAIR)
        if not sep or not num.isdigit():
            continue
        out.append((name, int(num)))
    return out


def summarize(encoded) -> str:
    """기록된 행들을 사람이 읽는 한 장으로. **판정 문구를 안 쓴다** — 숫자를 보고 사람이 정한다.

    두 가지를 나란히 낸다. 합계만 내면 **큰 질문 몇 개가 분포를 지배**하고, 쏠림만 내면
    **얼마나 많이 왔는지**가 사라진다. §5.3 이 정할 문턱은 둘 중 어느 쪽에도 걸릴 수 있다.
    """
    rows = [counts_ for c in encoded if (counts_ := decode(c))]
    if not rows:
        return "근거 점유율: 기록된 행이 없다.\n(이 칸은 migration 038 부터 쌓인다 — 그 전 행은 비어 있다.)"

    total: dict[str, int] = {}
    solo: dict[str, int] = {}
    mixed = 0
    for pairs in rows:
        for name, n in pairs:
            total[name] = total.get(name, 0) + n
        if len(pairs) == 1:
            solo[pairs[0][0]] = solo.get(pairs[0][0], 0) + 1
        else:
            mixed += 1

    grand = sum(total.values())
    enough = len(rows) >= MIN_SAMPLE
    # ⚠ 칸 맞춤을 안 한다. 이름에 한글이 섞이면 폭이 어긋나고, 어긋난 표는 읽는 사람이
    # 숫자를 잘못 짚는다 — `persistence-health` 가 같은 이유로 표를 버렸다.
    out = [f"근거 점유율 — 질문 {len(rows)}건 · 조각 {grand}개", "",
           "  조각 합계"]
    for name, n in sorted(total.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f"    {name} — {n}개" + (f" ({n / grand:.1%})" if enough else ""))
    out += ["", "  질문당 쏠림 — 근거가 **한 코퍼스에서만** 온 질문"]
    for name, n in sorted(solo.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f"    {name} — {n}건")
    out.append(f"    섞임 — {mixed}건")
    if not enough:
        out += ["", f"⚠ 질문 {len(rows)}건은 비율을 낼 표본이 아니다({MIN_SAMPLE}건부터 낸다). "
                    "개수만 읽어라."]
    out += ["", "⚠ 문턱은 없다 — 이 분포를 보고 사람이 정한다 (SPEC-nexus-design-corpus-cutover §5.3)."]
    return "\n".join(out)

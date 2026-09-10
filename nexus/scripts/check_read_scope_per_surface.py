"""표면마다 **실제로 무엇에 닿는가** — 선언한 서빙 코퍼스를 세어서 확인한다.

⛔ **왜 있나 (`OPEN.md` A34, 실측 2026-09-03).** 컷오버가 `slack-bot` 하나에만 정본을 읽을
권한을 줬고, 웹·CLI 는 `local-dev` principal 을 탄다. 그래서 `design_docs` 의 활성 문서
122건이 사람이 쓰는 표면에서 근거로 나올 수 **없었다**. 설정은 문법적으로 맞았고, 검사는
전부 초록이었고, 그 경로로 아무도 안 지나갔다.

⛔ **지금 있는 회귀 검사가 이것을 못 본다.** `test_read_scope_reaches_every_enrichment.py` 는
범위가 **목록일 때 보강이 죽지 않는가**를 본다(A33 의 잔여). 범위 자체가 **어느 코퍼스를
빼먹고 있는가**는 아무도 안 센다. 두 질문은 다르다 — 앞은 모양이고 뒤는 도달 범위다.

⭐ **표면 단위로 판정한다. 코퍼스 단위로 하면 진짜 결함을 놓친다.** 이 검사를 처음에는
「서빙 코퍼스에 닿는 표면이 **하나라도** 있는가」로 만들었는데, 2026-09-03 의 실제 상태가
바로 `slack-bot` 은 닿고 `local-dev` 는 못 닿는 것이었다. 그 규칙이면 그날 이 검사는
**초록**이다. 결함은 코퍼스가 고아가 된 것이 아니라 **어떤 표면이 빠진 것**이었다.

⭐ **문자열 비교로는 부족하다.** 범위에 `design_docs` 가 적혀 있는 것과 그 이름으로 실제
청크가 나오는 것은 다른 사실이다. 그래서 이 검사는 선언과 설정을 대조하는 데서 멈추지 않고,
**답변 경로가 쓰는 그 술어**(`search.scope_sql.tenant_predicate`)로 청크를 센다. 술어가
깨지면 수가 깨진다 — 여기서 SQL 을 새로 쓰면 셋째 진실이 생긴다.

⚠ **대조군 둘이 없으면 이 검사도 빈 집합에 대고 0 을 외치게 된다.**

* **양성** — 서빙 표면 중 적어도 하나는 0 보다 큰 수를 내야 한다.
* **음성** — 활성 청크가 있는데 그 표면의 범위 **밖**인 테넌트는 0 을 내야 한다. 여기서
  0 이 아니면 술어가 안 거르는 것이고, 그러면 위의 모든 수가 아무 말도 못 한다.

음성 대조군을 세울 수 없으면(활성 청크가 있는 테넌트가 전부 어느 범위에나 들어 있으면)
판정을 내지 않는다.

읽기 전용. 코퍼스를 건드리지 않는다.

    docker exec nexus-app python -u scripts/check_read_scope_per_surface.py

종료 코드: `0` 이상 없음 · `1` 결함 · `76` 판정 불가.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":          # cp949 콘솔이 ⚠ 에서 죽는다
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus import db  # noqa: E402
from nexus.auth import AuthConfig, Principal  # noqa: E402
from nexus.search.scope_sql import tenant_predicate  # noqa: E402


def _load_config() -> dict:
    """`api.py` · `cli.py` 와 같은 방식으로 `config.yaml` 을 읽는다.

    ⚠ 공용 로더가 없어서 세 곳이 같은 여섯 줄을 갖고 있다. 여기서 다른 경로나 다른
    기본값을 쓰면 이 검사가 앱과 다른 설정을 보게 되므로 그 여섯 줄을 그대로 맞춘다.
    """
    f = Path("config.yaml")
    if not f.exists():
        return {}
    with open(f, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def served_corpora(config: dict | None) -> set[str]:
    """`config.index.served_corpora` — **답변에 쓰이라고 유지하는** 테넌트.

    ⛔ 추론하지 않는다. 「활성 문서가 있으니 서빙 대상이겠지」로 읽으면 평가 팩과 실험
    테넌트가 전부 서빙 대상이 되고, 그러면 이 검사는 매번 붉고 곧 꺼진다. 옆의
    `coverage_exempt_tenants` 가 선언식인 것과 같은 이유다.
    """
    return set(((config or {}).get("index") or {}).get("served_corpora") or [])


def serving_surfaces(config: dict | None) -> set[str]:
    """`config.auth.serving_surfaces` — **사람의 질문에 답하는** principal 이름들.

    평가·실험 principal 은 여기 없다. 그것들의 좁은 범위는 결함이 아니라 설계다.
    """
    return set(((config or {}).get("auth") or {}).get("serving_surfaces") or [])


def read_scopes(auth: AuthConfig) -> dict[str, tuple[str, ...]]:
    """표면마다 읽기 범위. **앱이 principal 을 만드는 그 경로**에서 받는다.

    `local-dev`(웹·CLI)와 `slack-bot` 은 `config.yaml` 에 없고 env 로 주입되므로, 여기서
    env 를 다시 읽으면 배포와 어긋난다. `AuthConfig.from_dict` 가 이미 합쳐 준 목록을 쓴다.
    """
    out: dict[str, tuple[str, ...]] = {}
    for entry in auth.principals or []:
        p = Principal(
            name=str(entry.get("name", "unknown")),
            tenant=str(entry.get("tenant", "default")),
            clearance=str(entry.get("clearance", "PUBLIC")),
            read_tenants=tuple(str(t) for t in (entry.get("read_tenants") or [])),
        )
        out[p.name] = p.read_scope
    return out


def verdict(*, scopes: dict[str, tuple[str, ...]], serving: set[str], served: set[str],
            active: dict[str, int], reach: dict[tuple[str, str], int],
            negative: tuple[str, str, int] | None) -> dict:
    """**판정을 내도 되는가, 그리고 무엇이 결함인가.** 순수·결정론.

    `active` 는 테넌트별 활성 청크 수, `reach` 는 `(표면, 테넌트) -> 술어로 센 청크 수`,
    `negative` 는 `(표면, 범위 밖 테넌트, 술어가 낸 수)` 이고 그 수는 0 이어야 한다.

    ⚠ **선언됐지만 이 배포에 없는 서빙 표면은 건너뛴다.** 로컬 상자에 슬랙 토큰이 없는 것은
    결함이 아니다. 다만 선언된 것이 **하나도** 안 떠 있으면 판정하지 않는다.
    """
    if not scopes:
        return {"usable": False, "why": "principal 이 하나도 없다 — 셀 표면이 없다"}
    if not served:
        return {"usable": False,
                "why": "config.index.served_corpora 가 비었다 — 무엇에 닿아야 하는지 "
                       "선언되지 않았으면 판정할 것이 없다"}
    if not serving:
        return {"usable": False,
                "why": "config.auth.serving_surfaces 가 비었다 — 어느 표면이 답하는지 "
                       "선언되지 않으면 「빠졌다」를 표현할 수 없다"}
    present = sorted(serving & set(scopes))
    if not present:
        return {"usable": False,
                "why": f"선언된 서빙 표면({', '.join(sorted(serving))})이 이 배포에 "
                       "하나도 없다 — 없는 표면의 범위는 셀 수 없다"}
    if not any(active.values()):
        return {"usable": False,
                "why": "활성 청크가 있는 테넌트가 없다 — 빈 코퍼스에 대고 0 을 결과로 "
                       "내지 않는다"}
    if negative is None:
        return {"usable": False,
                "why": "음성 대조군을 세울 수 없다 — 활성 청크가 있으면서 어느 표면의 범위 "
                       "밖인 테넌트가 없다. 술어가 거르는지 확인하지 못했다"}
    surface, outside, leaked = negative
    if leaked:
        return {"usable": False,
                "why": f"음성 대조군이 샌다 — {surface!r} 의 범위 밖인 {outside!r} 에서 "
                       f"청크 {leaked}개가 나왔다. 술어가 안 거르므로 위의 수는 전부 "
                       "아무 말도 못 한다"}
    if not any(reach.get((s, t), 0) for s in present for t in scopes.get(s, ())):
        return {"usable": False,
                "why": "서빙 표면 중 청크 하나에 닿은 것이 없다 — 양성 대조군이 서지 않는다"}

    # **표면마다** 센다. 코퍼스가 고아인지가 아니라 그 표면이 빠졌는지가 결함이다.
    missing = sorted((s, t) for s in present for t in sorted(served)
                     if not reach.get((s, t), 0))
    empty_scope = sorted(
        {(s, t) for s, sc in scopes.items() for t in sc if active.get(t, 0) == 0})
    return {"usable": True, "missing": missing, "empty_scope": empty_scope,
            "checked": present, "why": ""}


async def _reachable(tenant: str, scope: str | tuple[str, ...]) -> int:
    """`scope` 를 읽기 범위로 놓았을 때 답변 경로의 술어가 세는 `tenant` 의 활성 청크 수.

    술어를 여기서 다시 쓰지 않는 것이 요점이다 — `tenant_predicate` 가 원소 하나에는
    `= $n`, 여럿에는 `= ANY($n)` 을 내고, 그 분기가 깨진 적이 실제로 있다(A33).
    """
    sql, value = tenant_predicate("c.tenant", 1, scope)
    row = await db.fetch_one(
        f"""
        SELECT count(*) AS n
          FROM chunks c
          JOIN documents d ON d.rid = c.doc_rid
         WHERE {sql} AND d.status = 'active' AND c.tenant = $2
        """, value, tenant)
    return int(row["n"]) if row else 0


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    config = _load_config()
    auth = AuthConfig.from_dict(config)
    scopes = read_scopes(auth)
    served = served_corpora(config)
    serving = serving_surfaces(config)

    await db.get_pool()
    try:
        active = {r["tenant"]: int(r["n"]) for r in await db.fetch_all(
            """
            SELECT c.tenant, count(*) AS n
              FROM chunks c JOIN documents d ON d.rid = c.doc_rid
             WHERE d.status = 'active' GROUP BY c.tenant
            """)}

        # **범위 전체를 그대로** 넘긴다 — 원소가 둘이면 `= ANY($n)` 분기를 타야 한다.
        # 서빙 표면은 **선언된 코퍼스 전부**를 센다. 범위 안만 세면 빠진 것이 안 보인다 —
        # 범위 밖은 술어가 0 을 내고, 그 0 이 곧 이 검사가 찾는 결함이다.
        reach: dict[tuple[str, str], int] = {}
        for surface, scope in scopes.items():
            wanted = set(scope) | (served if surface in serving else set())
            for t in sorted(wanted):
                reach[(surface, t)] = await _reachable(t, scope)

        # 음성 대조군 — 활성 청크가 있는데 이 표면의 범위 밖인 테넌트를 하나 고른다.
        negative: tuple[str, str, int] | None = None
        for surface, scope in sorted(scopes.items()):
            outside = sorted(t for t, n in active.items() if n and t not in scope)
            if outside:
                negative = (surface, outside[0], await _reachable(outside[0], scope))
                break

        v = verdict(scopes=scopes, serving=serving, served=served, active=active,
                    reach=reach, negative=negative)

        print(f"\n  선언된 서빙 코퍼스: {', '.join(sorted(served)) or '(없음)'}")
        print(f"  선언된 서빙 표면: {', '.join(sorted(serving)) or '(없음)'}")
        print(f"  이 배포의 표면 {len(scopes)}개\n")
        for surface, scope in sorted(scopes.items()):
            tag = " (서빙)" if surface in serving else ""
            print(f"    {surface}{tag}  범위 [{', '.join(scope)}]")
            for t in sorted(set(scope) | (served if surface in serving else set())):
                mark = "서빙" if t in served else "    "
                inside = " " if t in scope else "밖"
                print(f"        {mark}{inside} {t:18s} {reach.get((surface, t), 0):6d}")
        if negative:
            s, t, n = negative
            print(f"\n  음성 대조군: {s!r} 범위 밖의 {t!r} → {n} (0 이어야 한다)")

        if not v["usable"]:
            print(f"\n⛔ 판정을 내지 않는다 — {v['why']}")
            return 76

        if v["missing"]:
            print("\n⛔ 서빙 표면이 선언된 코퍼스에 못 닿는다:")
            for s, t in v["missing"]:
                print(f"    {s} → {t}")
            print("   선언을 지우든 그 표면의 읽기 범위를 넓히든, 둘 중 하나는 사람이 정한다.")
        if v["empty_scope"]:
            print("\n⚠ 범위가 빈 코퍼스를 가리킨다 (설정은 맞고 뒤에 아무것도 없다):")
            for s, t in v["empty_scope"]:
                print(f"    {s} → {t}")
        if not v["missing"] and not v["empty_scope"]:
            print(f"\n  이상 없음 — 서빙 표면 {len(v['checked'])}개가 선언된 코퍼스 "
                  f"{len(served)}개에 전부 닿는다.")
        return 1 if (v["missing"] or v["empty_scope"]) else 0
    finally:
        await db.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

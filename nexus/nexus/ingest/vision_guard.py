"""재적재가 **이미 읽어 둔 그림 텍스트를 조용히 지우는 것**을 막는다.

⛔ **왜 있나 (사고 2026-09-02).** 메타데이터 한 칸을 백필하려고 `ingest-notion --force` 를
돌렸다. `NEXUS_VISION` 은 **꺼짐이 기본**이고(그림이 공급자로 나가는 것은 코퍼스를 가진
배포가 하는 판단), 꺼져 있으면 적재가 그림 자리 표식을 빈 이미지로 지운다. 결과::

    청크          466 → 385
    machine_read   81 → 0

라이브 답변이 실제로 나빠졌다 — 같은 질문이 값을 답하다가 *"확인할 수 없습니다"* 로 기권했다.
경고도 확인 질문도 없었고, **끝났다는 출력만 초록이었다.**

ADR-0010 §4 는 마커가 벗겨져 추출 텍스트가 저자 텍스트로 세탁되는 것을 *"추출 안 하느니만
못하다"* 고 적었다. 이것은 그보다 나쁘다 — 세탁이 아니라 **삭제**다.

**조용히 지우는 것이 옳은 경우가 없다.** 그래서 거부한다. 이 리포는 같은 모양의 규율을 이미
갖고 있다(테스트 DB 는 스스로 버려도 된다고 선언해야 한다). 지우려면 선언해야 한다.
"""

from __future__ import annotations

#: 선언 없이 지나갈 수 없다. 값이 이것이면 운영자가 **알고** 지우는 것이다.
OVERRIDE_ENV = "NEXUS_VISION_ALLOW_DROP"

_LINES = (
    "거부: 이 코퍼스에 그림에서 읽은 청크가 {n}개 있는데 `NEXUS_VISION` 이 꺼져 있다.",
    "  지금 적재하면 그 청크들이 **지워진다** — 2026-09-02 에 실제로 466 → 385 로 지워졌고,",
    "  라이브 답변이 값을 답하다가 기권으로 바뀌었다.",
    "  · 되살리려면: NEXUS_VISION=on (판독은 캐시되어 있어 공급자 호출이 없을 수 있다)",
    "  · 정말 지우려면: {env}=1 을 함께 준다",
)


def vision_is_on(env: dict) -> bool:
    """`_fill_images` 와 **같은 판정**을 쓴다 — 사본을 두면 언젠가 갈린다."""
    return (env.get("NEXUS_VISION") or "off").strip().lower() == "on"


def allowed_to_drop(env: dict) -> bool:
    """운영자가 **알고** 지우겠다고 선언했는가."""
    return (env.get(OVERRIDE_ENV) or "").strip().lower() in ("1", "true", "on", "yes")


def refusal(n_machine_read: int, env: dict) -> str:
    """지우게 될 청크가 있으면 거부 사유, 없으면 빈 문자열.

    셋 다 참일 때만 문다: **판독이 꺼져 있고** · **지울 것이 있고** · **선언이 없다.**
    """
    if vision_is_on(env) or n_machine_read <= 0 or allowed_to_drop(env):
        return ""
    return "\n".join(_LINES).format(n=n_machine_read, env=OVERRIDE_ENV)


async def count_machine_read(tenant: str) -> int:
    """지울 수 있는 것이 몇 개인가. **함수로 떼어 둔 이유가 있다.**

    가드는 적재 경로 **앞**에 서므로, 그 경로를 DB 없이 도는 시험(루프 동일성·토큰 그룹핑)이
    이 조회에 걸린다. 이 리포는 *"진단을 요청 경로에 두지 마라"* 를 이미 한 번 CI 40분으로
    배웠다. 여기서는 조회를 없앨 수 없으므로 — 없으면 가드가 성립하지 않는다 — **갈아 끼울 수
    있는 자리**로 만든다. 프로덕션은 이 구현을 쓰고, 그 시험들은 이것만 대체한다.
    """
    from nexus import db

    return int(await db.fetch_val(
        "SELECT count(*) FROM chunks WHERE tenant = $1 AND status = 'active' "
        "AND provenance_tier = 'machine_read'", tenant) or 0)

"""Notion 연결 진단 — SPEC-nexus-notion-connection-health §4.1~§4.3.

토큰이 진짜인가, 등록된 root 에 정말 닿는가. Notion 에게 직접 묻고, **모르면 모른다고 한다.**

두 가지가 이 파일의 전부다:

  · `unknown` 은 절대 `unreachable` 로 무너지지 않는다. Notion 장애를 "당신의 페이지가
    사라졌다" 로 보고하면, 그 말을 믿은 사용자는 공유가 풀린 적 없는 페이지를 다시 공유하러 간다.
  · 토큰 값은 이 프로세스를 떠나지 않는다. 결과 객체에도, 예외 문자열에도, 응답에도.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import httpx

_API = "https://api.notion.com"
_VERSION = "2022-06-28"
_ROOT_TIMEOUT = 5.0
_MAX_CONCURRENCY = 8          # SPEC §4.1 (I-007)

# remedy 는 **할 일**만 담는다. 무엇이 잘못됐는지(진단)는 상태 이름이 말한다 — 둘을 한 문자열에
# 넣으면 표면마다 "볼 수 없음 — 이 페이지를 볼 수 없습니다 —…" 처럼 겹쳐 읽힌다.
REMEDY_UNREACHABLE = (
    "존재하지 않거나 integration 이 초대되지 않았습니다. "
    "Notion 에서 이 페이지의 연결(Connections)에 integration 을 추가하세요."
)
REMEDY_INVALID_ID = "페이지 id 형식이 잘못되었습니다. URL 을 다시 복사해 주세요."


class TokenState(str, Enum):
    NOT_CONFIGURED = "not_configured"
    INVALID = "invalid"
    OK = "ok"
    UNKNOWN = "unknown"


class RootState(str, Enum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    INVALID_ID = "invalid_id"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TokenHealth:
    state: TokenState
    integration: str | None = None
    workspace: str | None = None
    prefix: str = ""            # 앞 4자. `ntn_` 와 `secret_` 와 붙여넣기 쓰레기를 구분할 만큼만.


@dataclass(frozen=True)
class RootHealth:
    root_id: str
    state: RootState
    title: str | None = None
    remedy: str = ""


@dataclass(frozen=True)
class ConnectionHealth:
    token: TokenHealth
    roots: list[RootHealth] = field(default_factory=list)
    checked_at: str = ""


def redact(text: str, token: str) -> str:
    """토큰 값을 문자열에서 지운다. 패턴이 아니라 **값**으로 — 우리는 정확한 문자열을 안다.

    패턴 기반이면 다음 토큰 형식을 놓친다(`ntn_` 이전엔 `secret_` 이었다).
    """
    if not token or not text:
        return text
    return text.replace(token, "[REDACTED]")


def _title_of(body: dict) -> str | None:
    """페이지는 properties 안의 title 타입 속성에, 데이터베이스는 최상위 `title` 에 제목이 있다."""
    for prop in (body.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title") or []) or None
    top = body.get("title")
    if isinstance(top, list):
        return "".join(t.get("plain_text", "") for t in top) or None
    return None


async def _get(client: httpx.AsyncClient, path: str) -> httpx.Response | None:
    """응답 또는 None(전송 실패/타임아웃). 예외 문자열은 여기서 죽는다 — 밖으로 새지 않는다."""
    try:
        return await client.get(path, timeout=_ROOT_TIMEOUT)
    except httpx.HTTPError:
        return None


async def _probe_token(client: httpx.AsyncClient, prefix: str) -> TokenHealth:
    resp = await _get(client, "/v1/users/me")
    if resp is None:
        return TokenHealth(TokenState.UNKNOWN, prefix=prefix)
    if resp.status_code == 401:
        return TokenHealth(TokenState.INVALID, prefix=prefix)
    if resp.status_code != 200:
        return TokenHealth(TokenState.UNKNOWN, prefix=prefix)

    body = resp.json()
    return TokenHealth(
        TokenState.OK,
        integration=body.get("name") or None,
        workspace=(body.get("bot") or {}).get("workspace_name") or None,
        prefix=prefix,
    )


def _classify(page: httpx.Response | None, db: httpx.Response | None) -> RootState:
    """두 엔드포인트의 답을 하나의 상태로. 명시된 행이 아니면 전부 `unknown`."""
    for resp in (page, db):
        if resp is not None and resp.status_code == 200:
            return RootState.REACHABLE

    codes = {r.status_code for r in (page, db) if r is not None}
    if not codes:
        return RootState.UNKNOWN                    # 둘 다 전송 실패/타임아웃
    if codes <= {404, 403}:
        return RootState.UNREACHABLE                # 없거나 초대받지 않았다 — 사용자에겐 같은 말
    if codes <= {400}:
        return RootState.INVALID_ID
    return RootState.UNKNOWN                        # 429·5xx·혼합 — 모른다


async def _probe_root(client: httpx.AsyncClient, root_id: str) -> RootHealth:
    page = await _get(client, f"/v1/pages/{root_id}")

    # 200 이 **아닐 때마다** 데이터베이스로 다시 묻는다. 404 일 때만 재시도하면, 데이터베이스가
    # 400 을 돌려줄 경우 invalid_id 로 오판하고 사용자를 엉뚱한 곳으로 보낸다 (SPEC I-006).
    db = None
    if page is None or page.status_code != 200:
        db = await _get(client, f"/v1/databases/{root_id}")

    state = _classify(page, db)
    if state is RootState.REACHABLE:
        hit = page if (page is not None and page.status_code == 200) else db
        return RootHealth(root_id, state, title=_title_of(hit.json()))
    remedy = {
        RootState.UNREACHABLE: REMEDY_UNREACHABLE,
        RootState.INVALID_ID: REMEDY_INVALID_ID,
    }.get(state, "")
    return RootHealth(root_id, state, remedy=remedy)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def probe_connection(
    token: str,
    root_ids: list[str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ConnectionHealth:
    """토큰과 각 root 를 Notion 에 물어 확인한다. 절대 예외를 던지지 않는다.

    진단은 진단 대상과 함께 죽으면 안 된다 — Notion 이 통째로 내려가도 200 을 돌려주고,
    모든 것이 `unknown` 이라고 말한다.
    """
    prefix = token[:4]
    if not token:
        # Notion 을 부르지 않는다. 부를 이유가 없다.
        return ConnectionHealth(
            TokenHealth(TokenState.NOT_CONFIGURED),
            [RootHealth(r, RootState.UNKNOWN) for r in root_ids],
            _now(),
        )

    headers = {"Authorization": f"Bearer {token}", "Notion-Version": _VERSION}
    async with httpx.AsyncClient(base_url=_API, headers=headers, transport=transport) as client:
        tok = await _probe_token(client, prefix)

        # 토큰이 살아있지 않으면 root 는 건드리지 않는다. 전부 401 로 답할 테고, 그걸
        # unreachable 로 적으면 토큰의 죄를 페이지에 씌우는 것이다 (SPEC §5).
        if tok.state is not TokenState.OK:
            return ConnectionHealth(
                tok, [RootHealth(r, RootState.UNKNOWN) for r in root_ids], _now())

        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def bounded(rid: str) -> RootHealth:
            async with sem:
                return await _probe_root(client, rid)

        roots = list(await asyncio.gather(*(bounded(r) for r in root_ids)))

    return ConnectionHealth(tok, roots, _now())

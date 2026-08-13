"""대화 이력 — 무엇을 받고, 무엇을 거절하는가 (SPEC-nexus-multi-turn-retrieval §3.1).

**이 파일이 정본이다.** HTTP API 와 A2A 는 서로 다른 모양으로 이력을 받지만(Pydantic 모델 대
JSON-RPC `message.metadata`), 상한과 거절 규칙은 **한 곳에서만** 온다. 이 리포는 같은 규칙을
두 번 적었다가 곧바로 갈라진 적이 있다 — 등급 목록은 사본에만 `CONFIDENTIAL` 이 있어 게이트를
통과한 값이 SQL 캐스트에서 터졌고, 채점 규칙도 사본이었다가 하나로 합쳤다.

U2 에서 서버는 이력을 **받아서 버린다**. 동작 변화 0 이고, 여기서 사는 것은 상한뿐이다.
검색에 쓰는 것은 U3 다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 서버가 보는 최대 턴 수. **잠정값** — SPEC §5.3 이 하니스로 {2, 4, 8} 중에서 정한다.
#: 클라이언트에 맡기지 않는 이유: 표면마다 다른 값이 되고, 그 차이는 아무 데도 안 적힌다.
MAX_TURNS = 8

#: 이력 전체의 최대 바이트(UTF-8). 턴 **수**만 세면 한 턴이 수 MB 여도 통과한다.
MAX_BYTES = 8 * 1024

ROLES = ("user", "assistant")


class HistoryTooLarge(ValueError):
    """상한을 넘었다. 호출자 잘못이므로 413 / JSON-RPC invalid params 로 나간다."""


class MalformedHistory(ValueError):
    """이력의 모양이 계약과 다르다 — 리스트가 아니거나, 역할이 낯설거나, 내용이 문자열이 아니다."""


@dataclass(frozen=True)
class Turn:
    """대화 한 턴. 오래된 것부터 나열되며, **마지막 원소는 이번 질의가 아니다.**"""
    role: str
    content: str


def parse(raw) -> list[Turn]:
    """느슨한 입력(리스트-오브-딕트)을 `Turn` 목록으로. 계약을 어기면 예외를 던진다.

    **조용히 자르지 않는다.** 오래된 턴부터 버리면 클라이언트는 자기가 보낸 맥락의 절반이
    사라진 것을 관측할 수 없고, "상한은 서버에 있다" 는 사실이 아무 데도 안 드러난다. 자르는
    판단은 클라이언트가 명시적으로 한다 (SPEC §3.1).
    """
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise MalformedHistory("history 는 배열이어야 한다")
    turns: list[Turn] = []
    for i, item in enumerate(raw):
        if isinstance(item, Turn):
            turns.append(item)
            continue
        if not isinstance(item, dict):
            raise MalformedHistory(f"history[{i}] 가 객체가 아니다")
        role, content = item.get("role"), item.get("content")
        if role not in ROLES:
            raise MalformedHistory(f"history[{i}].role 이 {ROLES} 중 하나가 아니다: {role!r}")
        if not isinstance(content, str):
            raise MalformedHistory(f"history[{i}].content 가 문자열이 아니다")
        turns.append(Turn(role=role, content=content))
    return check(turns)


def byte_size(turns: list[Turn]) -> int:
    """이력 전체의 UTF-8 바이트. 한국어는 글자당 3바이트라 문자 수로 세면 상한이 3배가 된다."""
    return sum(len(t.content.encode("utf-8")) for t in turns)


def check(turns: list[Turn]) -> list[Turn]:
    """상한 검사. 통과하면 그대로 돌려주고, 넘으면 `HistoryTooLarge`."""
    if len(turns) > MAX_TURNS:
        raise HistoryTooLarge(
            f"이력이 {len(turns)}턴이다 — 서버 상한은 {MAX_TURNS}턴. "
            f"최근 {MAX_TURNS}턴만 보내라(자르는 판단은 클라이언트가 한다)")
    if (n := byte_size(turns)) > MAX_BYTES:
        raise HistoryTooLarge(
            f"이력이 {n}바이트다 — 서버 상한은 {MAX_BYTES}바이트")
    return turns

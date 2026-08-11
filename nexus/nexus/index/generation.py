"""이 코퍼스가 어느 임베딩 세대에 있는가 — SPEC-nexus-generation-of-record.

두 프로세스가 같은 `config.yaml` 을 읽고 서로 다른 세대로 해석했고, 어느 쪽도 상대를 알 방법이
없었다. 세대는 프로세스의 설정이 아니라 **코퍼스의 사실**이므로, 코퍼스가 있는 곳에 적힌다.

세 가지가 이 모듈의 판정을 정한다:

* **선언이지 추론이 아니다.** 어느 컬럼에 행이 더 많은가로 유도하지 않는다 — 컷오버 중에는
  다수가 곧 **떠나는** 세대다 (§3.1).
* **선언 없음 ≠ 기본값.** 아무도 결정하지 않은 상태는 위반할 결정이 없으므로 적재를 막지 않는다.
  대신 `nexus status` 가 지목한다 (§3.2·§3.5).
* **선언 시점에 검증한다.** 오타 난 컬럼을 받아 두면, 존재하지도 않는 컬럼 이름을 대며 모든
  적재를 영원히 거부하게 된다 (§3.1).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from nexus import db

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Generation:
    """한 테넌트의 세대 선언. `column`·`model` 이 함께 움직인다."""
    tenant: str
    column: str
    model: str
    declared_by: str = ""
    declared_at: object = None
    reason: str = ""

    def matches(self, column: str, model: str) -> bool:
        return self.column == column and self.model == model

    def render(self) -> str:
        return f"{self.column} / {self.model}"


class GenerationMismatch(RuntimeError):
    """이 프로세스가 해석한 세대가 코퍼스의 선언과 다르다. **쓰기 전에** 멈춘다."""


class InvalidDeclaration(ValueError):
    """선언 자체가 성립하지 않는다 — 모르는 컬럼이거나, 모델 차원이 컬럼과 다르다."""


def validate(column: str, model: str) -> tuple[str, str]:
    """선언을 쓰기 전에 검사한다. 통과한 (컬럼, 모델) 을 돌려준다.

    레지스트리를 **여기서 다시 정의하지 않는다** — 컬럼 화이트리스트와 모델 차원표는 이미 각각
    하나씩 있고, 세 번째 진실을 만들면 그 셋이 갈리는 날이 온다.
    """
    from nexus.index.vector_index import UnknownVectorColumn, dimensions_of
    from nexus.providers.embedding import MODEL_DIMENSIONS

    try:
        column_dim = dimensions_of(column)
    except (UnknownVectorColumn, KeyError) as e:
        raise InvalidDeclaration(str(e)) from None

    if model not in MODEL_DIMENSIONS:
        raise InvalidDeclaration(
            f"{model!r} 의 차원을 모른다 — MODEL_DIMENSIONS 에 없는 모델은 선언할 수 없다. "
            "모르는 모델을 세대로 박아 두면 그 뒤의 모든 적재가 검증 없이 통과한다.")
    if MODEL_DIMENSIONS[model] != column_dim:
        raise InvalidDeclaration(
            f"{model} 은 {MODEL_DIMENSIONS[model]} 차원인데 {column} 은 {column_dim} 차원이다. "
            "세대는 컬럼과 모델이 함께 움직인다.")
    return column, model


async def declare(tenant: str, column: str, model: str, declared_by: str,
                  reason: str = "") -> Generation:
    """세대를 선언한다(append). 이전 선언은 지우지 않는다 — 언제 바뀌었는지가 증거다."""
    column, model = validate(column, model)
    if not declared_by.strip():
        raise InvalidDeclaration("--by 가 필요하다. 누가 선언했는지 없는 기록은 감사에 못 쓴다.")

    await db.execute(
        "INSERT INTO index_generation_events (tenant, column_name, model, declared_by, reason) "
        "VALUES ($1, $2, $3, $4, $5)",
        tenant, column, model, declared_by.strip(), reason)
    logger.info("index_generation_declared", tenant=tenant, column=column, model=model,
                declared_by=declared_by.strip())
    return Generation(tenant, column, model, declared_by.strip(), None, reason)


async def current(tenant: str) -> Generation | None:
    """이 테넌트의 세대 선언. **없으면 None** — 기본값으로 대신하지 않는다."""
    row = await db.fetch_one(
        "SELECT tenant, column_name, model, declared_by, declared_at, reason "
        "FROM index_generation_events WHERE tenant = $1 ORDER BY id DESC LIMIT 1", tenant)
    if row is None:
        return None
    return Generation(row["tenant"], row["column_name"], row["model"],
                      row["declared_by"], row["declared_at"], row["reason"])


async def history(tenant: str | None = None) -> list[Generation]:
    """선언 이력(최신 순). 컷오버가 언제 일어났는지는 이 목록으로만 답할 수 있다."""
    if tenant:
        rows = await db.fetch_all(
            "SELECT tenant, column_name, model, declared_by, declared_at, reason "
            "FROM index_generation_events WHERE tenant = $1 ORDER BY id DESC", tenant)
    else:
        rows = await db.fetch_all(
            "SELECT tenant, column_name, model, declared_by, declared_at, reason "
            "FROM index_generation_events ORDER BY tenant, id DESC")
    return [Generation(r["tenant"], r["column_name"], r["model"], r["declared_by"],
                       r["declared_at"], r["reason"]) for r in rows]


async def assert_writable(tenant: str, column: str, model: str, *, what: str) -> Generation | None:
    """이 프로세스가 이 테넌트에 써도 되는가. **쓰기 전에** 부른다.

    선언이 있고 다르면 `GenerationMismatch` — 어느 쪽이 무엇인지와 고치는 명령을 담아서.
    선언이 없으면 경고 한 번(호출 한 번 = 실행 하나 · 테넌트 하나)을 남기고 통과시킨다.

    Args:
        what: 무엇이 쓰려 하는지 (메시지에 들어간다 — "ingest" · "reembed").
    """
    declared = await current(tenant)
    if declared is None:
        logger.warning("index_generation_undeclared", tenant=tenant, what=what,
                       resolved=f"{column} / {model}",
                       hint=f"nexus generation declare --tenant {tenant} "
                            f"--column {column} --model {model} --by <who>")
        return None
    if not declared.matches(column, model):
        raise GenerationMismatch(
            f"{what} 가 해석한 세대는 {column} / {model} 인데, 테넌트 {tenant!r} 의 코퍼스는 "
            f"{declared.render()} 로 선언돼 있다 (선언: {declared.declared_by}).\n"
            f"이대로 쓰면 검색되지 않는 컬럼에 적재된다 — 2026-08-10 에 그렇게 됐다.\n"
            f"  · 이 셸이 배포와 같은 세대를 보게 하라 (컨테이너 안에서 실행하거나 "
            f"NEXUS_EMBEDDING_MODEL/NEXUS_EMBEDDING_COLUMN 을 맞춰라)\n"
            f"  · 정말로 세대를 바꾸는 것이라면: "
            f"nexus reembed run --change-generation --column {column} --model {model} "
            f"--tenant {tenant} --by <who>")
    return declared

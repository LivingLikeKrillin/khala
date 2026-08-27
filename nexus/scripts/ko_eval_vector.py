"""평가용 벡터 저장소 — 모델별 실험군, 거부 회계, 정확 스캔
(SPEC-nexus-korean-embedding-comparison §4.1~§4.2).

프로덕션 `chunks.embedding` 은 건드리지 않는다. 768 과 1024 를 나란히 두려면 차원 없는 `vector`
컬럼이 필요하고, 그건 색인이 안 걸린다 — 1,900청크 정확 스캔이 공짜에 가까우니 오히려 설계다.
ivfflat 후보 집합 흔들림이 비교에 섞이지 않는다.

**해시가 둘인 이유**: 실험군마다 지시문 프리픽스가 달라서(`search_document: ` vs 없음) "실제 보낸
문자열" 해시는 두 실험군이 절대 같을 수 없다. 그래서 공용 입력(프리픽스 이전)은 `input_sha256`,
실험군이 실제 보낸 것은 `payload_sha256` 으로 나눈다. 전자는 "두 실험군이 같은 것을 봤나" 를, 후자는
"이 실험군이 지금 만들 문자열과 같은가" 를 지킨다.

**거부는 중단이 아니라 회계다**: Ollama 는 창을 넘는 입력을 잘라서 성공시키지 않고 **거부**하고,
프로덕션은 그걸 NULL 임베딩으로 흡수한다(청크가 벡터 검색에서 조용히 사라진다). 평가도 같은
상태를 재야 하므로 거부를 행으로 남기고 커버리지로 센다. **조용한 절단은 여전히 중단 사유다.**
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS ko_eval_embeddings (
    model          TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    pack           TEXT NOT NULL,
    chunk_rid      TEXT NOT NULL,
    status         TEXT NOT NULL,
    refusal_reason TEXT,
    input_sha256   TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    embedding      vector,
    PRIMARY KEY (model, tenant, pack, chunk_rid),
    CHECK ((status = 'embedded' AND embedding IS NOT NULL AND refusal_reason IS NULL)
        OR (status = 'refused'  AND embedding IS NULL     AND refusal_reason IS NOT NULL))
)
"""

#: 모델 레지스트리 — 기대 차원과 지시문 형식. 본문에 리터럴로 적지 않는다.
MODELS: dict[str, dict] = {
    "nomic-embed-text": {
        "dim": 768,
        "document_prefix": "search_document: ",     # nomic 모델 카드의 지시문 형식
        "query_prefix": "search_query: ",
    },
    "KURE-v1": {
        "dim": 1024,
        "document_prefix": "",                      # 카드에 지시문 없음 (핀된 리비전 기준)
        "query_prefix": "",
    },
}

EMBEDDED = "embedded"
REFUSED = "refused"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


input_hash = sha256          # 이름으로 의도를 남긴다: 프리픽스 이전 공용 입력


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


@dataclass
class EmbedRow:
    """한 청크에 대한 한 실험군의 결과. 임베딩됐거나, 거부됐거나 — 그 사이는 없다."""
    chunk_rid: str
    input_sha256: str
    payload_sha256: str
    embedding: list[float] | None = None
    refusal_reason: str | None = None

    @property
    def status(self) -> str:
        return EMBEDDED if self.embedding is not None else REFUSED


@dataclass
class ArmProblem:
    model: str
    reason: str

    def __str__(self) -> str:
        return f"{self.model}: {self.reason}"


@dataclass
class Coverage:
    """판정보다 **위에** 적히는 숫자 (§4.3). 한 실험군이 코퍼스의 1/8을 못 먹으면 재현율 표를
    like-for-like 로 읽으면 안 된다."""
    model: str
    embedded: int
    refused: int

    @property
    def total(self) -> int:
        return self.embedded + self.refused

    def __str__(self) -> str:
        pct = 100 * self.embedded / self.total if self.total else 0
        return f"{self.model}: {self.embedded}/{self.total} ({pct:.1f}%)"


#: 이 테이블이 가져야 할 컬럼. 스키마가 바뀌었는데 `CREATE TABLE IF NOT EXISTS` 는 아무 말도
#: 하지 않는다 — 예전 모양 위에서 임베딩을 다 돌린 뒤 마지막 INSERT 에서 죽는 것이 그 대가다.
REQUIRED_COLUMNS = {"model", "tenant", "pack", "chunk_rid", "status", "refusal_reason",
                    "input_sha256", "payload_sha256", "embedding"}


async def ensure_table(con) -> None:
    """테이블을 만들고, **이미 있다면 모양이 맞는지 확인한다.**

    평가 전용 테이블이라 지워도 되지만, 지우는 것은 사람이 결정한다 — 조용히 DROP 하면 방금 몇
    분씩 걸려 만든 실험군이 소리 없이 사라진다.
    """
    await con.execute(CREATE_SQL)
    cols = {r["column_name"] for r in await con.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name='ko_eval_embeddings'")}
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise RuntimeError(
            f"ko_eval_embeddings 의 스키마가 예전 모양이다 (없는 컬럼: {sorted(missing)}). "
            "평가 전용 테이블이니 지우고 다시 만들면 된다: "
            "DROP TABLE ko_eval_embeddings;")


async def replace_arm(con, model: str, tenant: str, pack: str, rows: list[EmbedRow]) -> Coverage:
    """한 실험군을 통째로 갈아끼운다 — 병합하지 않는다(세대 혼재 방지)."""
    expected = MODELS[model]["dim"]
    for r in rows:
        if r.embedding is not None and len(r.embedding) != expected:
            raise ValueError(
                f"{model}: 차원 {len(r.embedding)} 이 레지스트리의 {expected} 와 다르다 — "
                "자르거나 채우지 않고 중단한다")

    await ensure_table(con)
    await con.execute(
        "DELETE FROM ko_eval_embeddings WHERE model=$1 AND tenant=$2 AND pack=$3",
        model, tenant, pack)
    await con.executemany(
        "INSERT INTO ko_eval_embeddings (model, tenant, pack, chunk_rid, status, refusal_reason, "
        "input_sha256, payload_sha256, embedding) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::vector)",
        [(model, tenant, pack, r.chunk_rid, r.status, r.refusal_reason,
          r.input_sha256, r.payload_sha256,
          to_pgvector(r.embedding) if r.embedding is not None else None) for r in rows])
    return Coverage(model,
                    sum(1 for r in rows if r.status == EMBEDDED),
                    sum(1 for r in rows if r.status == REFUSED))


async def coverage(con, model: str, tenant: str, pack: str) -> Coverage:
    row = await con.fetchrow(
        "SELECT count(*) FILTER (WHERE status='embedded') e, count(*) FILTER (WHERE status='refused') r "
        "FROM ko_eval_embeddings WHERE model=$1 AND tenant=$2 AND pack=$3", model, tenant, pack)
    return Coverage(model, row["e"], row["r"])


async def verify_arm(con, model: str, tenant: str, pack: str,
                     expected: dict[str, tuple[str, str]]) -> list[ArmProblem]:
    """채점 전 검사. `expected` = {chunk_rid: (input_sha256, payload_sha256)} — 지금 만들면 나올 값.

    임베딩된 것과 거부된 것을 합쳐 팩의 청크 수와 맞아야 한다. 둘 중 어느 쪽도 아닌 청크는
    커버리지가 아니라 **설명되지 않는 구멍**이라 중단한다.
    """
    problems: list[ArmProblem] = []
    rows = await con.fetch(
        "SELECT chunk_rid, status, input_sha256, payload_sha256 FROM ko_eval_embeddings "
        "WHERE model=$1 AND tenant=$2 AND pack=$3", model, tenant, pack)
    have = {r["chunk_rid"]: r for r in rows}

    if len(have) != len(expected):
        problems.append(ArmProblem(
            model, f"행 {len(have)}건(임베딩+거부) ≠ 팩의 현재 청크 {len(expected)}건"))

    orphans = await con.fetch(
        "SELECT e.chunk_rid FROM ko_eval_embeddings e "
        "LEFT JOIN chunks c ON c.rid = e.chunk_rid AND c.tenant = e.tenant "
        "WHERE e.model=$1 AND e.tenant=$2 AND e.pack=$3 AND c.rid IS NULL LIMIT 5",
        model, tenant, pack)
    if orphans:
        problems.append(ArmProblem(
            model, f"살아 있는 청크가 없는 행 {len(orphans)}건 이상 (예: {orphans[0]['chunk_rid']}) "
                   "— 이전 적재본의 잔재다"))

    missing = [rid for rid in expected if rid not in have]
    if missing:
        problems.append(ArmProblem(model, f"임베딩도 거부도 없는 청크 {len(missing)}건 (예: {missing[0]})"))

    bad_input = [rid for rid, (h, _) in expected.items()
                 if rid in have and have[rid]["input_sha256"] != h]
    if bad_input:
        problems.append(ArmProblem(
            model, f"공용 입력이 지금 만들 문자열과 다르다 ({len(bad_input)}건, 예: {bad_input[0]})"))

    bad_payload = [rid for rid, (_, h) in expected.items()
                   if rid in have and have[rid]["payload_sha256"] != h]
    if bad_payload:
        problems.append(ArmProblem(
            model, f"이 실험군이 보낸 문자열이 지금 만들 것과 다르다 ({len(bad_payload)}건, 예: {bad_payload[0]})"))
    return problems


async def arms_saw_the_same_inputs(con, tenant: str, pack: str) -> list[str]:
    """두 실험군의 **공용 입력** 집합이 같은지 (§4.3). 다르면 그건 모델 비교가 아니다."""
    rows = await con.fetch(
        "SELECT model, chunk_rid, input_sha256 FROM ko_eval_embeddings WHERE tenant=$1 AND pack=$2",
        tenant, pack)
    per_model: dict[str, set] = {}
    for r in rows:
        per_model.setdefault(r["model"], set()).add((r["chunk_rid"], r["input_sha256"]))
    models = sorted(per_model)
    problems = []
    for other in models[1:]:
        if per_model[other] != per_model[models[0]]:
            diff = len(per_model[other] ^ per_model[models[0]])
            problems.append(f"{models[0]} 과 {other} 가 다른 입력을 봤다 ({diff}건 차이)")
    return problems


async def vector_search(con, model: str, tenant: str, pack: str, query_vector: list[float],
                        top_k: int = 20) -> list[tuple[str, int]]:
    """정확 스캔. 거부된 행은 애초에 후보가 아니다(프로덕션에서 NULL 임베딩이 그렇듯)."""
    rows = await con.fetch(
        "SELECT chunk_rid FROM ko_eval_embeddings "
        "WHERE model=$1 AND tenant=$2 AND pack=$3 AND status='embedded' "
        "ORDER BY embedding <=> $4::vector, chunk_rid LIMIT $5",
        model, tenant, pack, to_pgvector(query_vector), top_k)
    return [(r["chunk_rid"], i + 1) for i, r in enumerate(rows)]


async def refused_chunks(con, model: str, tenant: str, pack: str) -> set[str]:
    """비교가능 부분집합(§4.7)을 만들 때 쓴다 — 이 실험군이 먹지 못한 청크들."""
    rows = await con.fetch(
        "SELECT chunk_rid FROM ko_eval_embeddings "
        "WHERE model=$1 AND tenant=$2 AND pack=$3 AND status='refused'", model, tenant, pack)
    return {r["chunk_rid"] for r in rows}

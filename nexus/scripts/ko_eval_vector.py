"""평가용 벡터 다리 — 정확 스캔·모델별 저장소 (SPEC-nexus-korean-embedding-comparison §4.1~§4.2).

프로덕션 `chunks.embedding` 은 **건드리지 않는다.** 768 과 1024 를 한 테이블에 나란히 두려면
차원 없는 `vector` 컬럼이 필요하고, 그건 색인이 안 걸린다 — 그게 오히려 설계다. 1,900청크를
정확 스캔하는 건 공짜에 가깝고, 그 대가로 ivfflat(ANN)의 후보 집합 흔들림이 비교에 섞이지 않는다.

**스테일 arm 이 조용히 채점되는 것**이 여기서 가장 위험하다. `chunk_rid` 는 테넌트를 품은 uri 에서
나오고 하니스는 실행마다 청크를 지웠다 다시 넣는다 — 이전 적재본의 임베딩이 남아 있으면 개수는
맞는데 가리키는 청크가 없다. 그래서 세 가지를 채점 전에 본다: 살아 있는 청크와의 조인 · 런타임에
센 청크 수(리터럴 금지) · 임베딩한 문자열의 해시.
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
    input_sha256   TEXT NOT NULL,
    embedding      vector NOT NULL,
    PRIMARY KEY (model, tenant, chunk_rid)
)
"""

#: 모델 레지스트리 — 기대 차원과 지시문 형식. **본문에 리터럴로 적지 않는다** (SPEC §4.4, I-014).
#: 관측 차원이 여기와 다르면 중단한다. 프리픽스는 하니스 설정이며 프로덕션 경로를 건드리지 않는다.
MODELS: dict[str, dict] = {
    "nomic-embed-text": {
        "dim": 768,
        "document_prefix": "search_document: ",   # nomic 모델 카드의 지시문 형식
        "query_prefix": "search_query: ",
    },
    "KURE-v1": {
        "dim": 1024,
        "document_prefix": "",                    # 카드에 지시문 없음 (2026-08-03 확인)
        "query_prefix": "",
    },
}


def input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


@dataclass
class ArmProblem:
    """스테일/불완전 arm 의 사유. 채점 전에 던진다 — 부분 arm 은 결과가 아니다."""
    model: str
    reason: str

    def __str__(self) -> str:
        return f"{self.model}: {self.reason}"


async def ensure_table(con) -> None:
    await con.execute(CREATE_SQL)


async def replace_arm(con, model: str, tenant: str, pack: str,
                      rows: list[tuple[str, str, list[float]]]) -> None:
    """한 모델의 arm 을 **통째로** 갈아끼운다 — 병합하지 않는다(세대 혼재 사고 방지, §5)."""
    expected = MODELS[model]["dim"]
    for _, _, vec in rows:
        if len(vec) != expected:
            raise ValueError(
                f"{model}: 차원 {len(vec)} 이 레지스트리의 {expected} 와 다르다 — "
                "자르거나 채우지 않고 중단한다")

    await ensure_table(con)
    await con.execute("DELETE FROM ko_eval_embeddings WHERE model=$1 AND tenant=$2", model, tenant)
    await con.executemany(
        "INSERT INTO ko_eval_embeddings (model, tenant, pack, chunk_rid, input_sha256, embedding) "
        "VALUES ($1,$2,$3,$4,$5,$6::vector)",
        [(model, tenant, pack, rid, h, to_pgvector(vec)) for rid, h, vec in rows])


async def verify_arm(con, model: str, tenant: str,
                     expected_inputs: dict[str, str]) -> list[ArmProblem]:
    """채점 전 검사 (§4.1). `expected_inputs` = {chunk_rid: input_sha256} — 지금 임베딩한다면 나올 값."""
    problems: list[ArmProblem] = []
    rows = await con.fetch(
        "SELECT chunk_rid, input_sha256 FROM ko_eval_embeddings WHERE model=$1 AND tenant=$2",
        model, tenant)
    have = {r["chunk_rid"]: r["input_sha256"] for r in rows}

    if len(have) != len(expected_inputs):
        problems.append(ArmProblem(model, f"행 {len(have)}건 ≠ 팩의 현재 청크 {len(expected_inputs)}건"))

    orphans = await con.fetch(
        "SELECT e.chunk_rid FROM ko_eval_embeddings e "
        "LEFT JOIN chunks c ON c.rid = e.chunk_rid AND c.tenant = e.tenant "
        "WHERE e.model=$1 AND e.tenant=$2 AND c.rid IS NULL LIMIT 5", model, tenant)
    if orphans:
        problems.append(ArmProblem(
            model, f"살아 있는 청크가 없는 임베딩 {len(orphans)}건 이상 (예: {orphans[0]['chunk_rid']}) "
                   "— 이전 적재본의 잔재다"))

    mismatched = [rid for rid, h in expected_inputs.items() if have.get(rid) not in (None, h)]
    if mismatched:
        problems.append(ArmProblem(
            model, f"임베딩한 문자열이 지금 만들 문자열과 다르다 ({len(mismatched)}건, 예: {mismatched[0]})"))

    missing = [rid for rid in expected_inputs if rid not in have]
    if missing:
        problems.append(ArmProblem(model, f"임베딩이 없는 청크 {len(missing)}건 (예: {missing[0]})"))
    return problems


async def vector_search(con, model: str, tenant: str, query_vector: list[float],
                        top_k: int = 20) -> list[tuple[str, int]]:
    """정확 스캔. `chunk_rid` 2차 키로 동점까지 전순서 (키워드 다리와 같은 이유)."""
    rows = await con.fetch(
        "SELECT chunk_rid FROM ko_eval_embeddings "
        "WHERE model=$1 AND tenant=$2 "
        "ORDER BY embedding <=> $3::vector, chunk_rid "
        "LIMIT $4",
        model, tenant, to_pgvector(query_vector), top_k)
    return [(r["chunk_rid"], i + 1) for i, r in enumerate(rows)]

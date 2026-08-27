"""ADR-0008 §2.6 재현 아티팩트 — nori 를 khala 의 한국어 리콜 fixture 에 걸어본 탐색 실행.

이 파일은 **테스트가 아니고, 측정도 아니다.** ADR-0008 §2.6 이 기록한 탐색 실행을 나중에
누가 그대로 재현할 수 있게 두는 일회성 스크립트다. 그 실행은 mecab 과의 비교로 쓸 수 없다 —
교란 변수가 최소 네 개다:

  1. 엔진·스코러가 다르다 — Nexus 는 Postgres `to_tsquery('simple', …)` + `ts_rank_cd`
     (nexus/search/hybrid.py), 여기는 OpenSearch `match` + BM25.
  2. 질의 의미가 다르다 — Nexus 의 키워드 다리는 tokens_to_tsquery 조립에 좌우되고,
     `match` 는 OR 이다.
  3. 코퍼스(5문서)가 조회 창(size=20)보다 작다 — **미스가 구조적으로 거의 불가능하다.**
     그래서 '미스 0' 은 결과가 아니라 산술이다.
  4. 기대 어휘가 mecab 의 분해에서 못박혀 있어, 다른 토크나이저의 회귀를 원리적으로
     탐지하지 못한다 (예: nori 는 '엔티티' 를 '엔'/'티티' 로 쪼개지만 그 질의의 판정은
     '식별' 에 걸려 있어 점수가 안 떨어진다).

즉 이 스크립트가 뭘 출력하든 **동등성의 근거가 되지 않는다.** 진짜 비교는 ADR-0008 §5(b)
가 요구하는 평가셋이 있어야 가능하다. 여기 두는 이유는 그때 무엇을 피해야 하는지 남기기
위해서다.

실행:

    docker run -d --name nori -p 19200:9200 \
        -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true \
        opensearchproject/opensearch:2.17.1
    docker exec nori bin/opensearch-plugin install --batch analysis-nori
    docker restart nori
    cd nexus && python scripts/adr0008_nori_recall.py
"""

import json
import sys
import urllib.request
from pathlib import Path

# 코퍼스와 질의는 리콜 스위트에서 **가져온다**. 복붙하면 조용히 갈라지고, 그러면 두 평가 하니스로 잰
# 숫자가 되어 재현이라는 말이 성립하지 않는다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_search_recall import (  # noqa: E402
    DOCS,
    KEYWORD_MISSES_MAX,
    KEYWORD_MRR_MIN,
    QUERIES,
)

OS_URL = "http://localhost:19200"
INDEX = "adr0008_nori_recall"


def _req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{OS_URL}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    try:
        _req("DELETE", f"/{INDEX}")
    except Exception:
        pass

    # Onyx 는 analyzer 를 색인/검색 양쪽에 건다 (backend/onyx/document_index/opensearch/schema.py).
    _req("PUT", f"/{INDEX}", {
        "settings": {
            "index": {"number_of_shards": 1, "number_of_replicas": 0},
            "analysis": {"analyzer": {"korean": {"type": "nori"}}},
        },
        "mappings": {"properties": {"content": {"type": "text", "analyzer": "korean"}}},
    })
    for key, text in DOCS.items():
        _req("PUT", f"/{INDEX}/_doc/{key}?refresh=true", {"content": text})

    print(f"코퍼스 {len(DOCS)}문서 · 질의 {len(QUERIES)}건 "
          f"(스위트 하한: 미스≤{KEYWORD_MISSES_MAX}, MRR≥{KEYWORD_MRR_MIN})")
    print("주의: 아래 숫자는 mecab 과 비교할 수 없다 — 모듈 docstring 의 교란 변수 4개 참조.\n")

    print("1. 토큰화 — 기대 어휘가 nori 토큰에 있는가")
    for query, _gold, lexeme in QUERIES:
        tokens = [t["token"] for t in _req(
            "POST", f"/{INDEX}/_analyze", {"analyzer": "korean", "text": query})["tokens"]]
        print(f"  [{'OK  ' if lexeme in tokens else 'MISS'}] {query!r} "
              f"기대={lexeme!r} 토큰={tokens}")

    print("\n2. 정답 문서 순위 (미스는 신호가 아님 — 교란 3 참조)")
    rr_sum = 0.0
    for query, gold, _lexeme in QUERIES:
        ids = [h["_id"] for h in _req(
            "POST", f"/{INDEX}/_search",
            {"query": {"match": {"content": query}}, "size": 20})["hits"]["hits"]]
        if gold in ids:
            rank = ids.index(gold) + 1
            rr_sum += 1.0 / rank
            print(f"  {query!r} → {gold} @rank {rank} / 반환 {len(ids)}건")
        else:
            print(f"  {query!r} → {gold} 없음 (반환: {ids})")

    print(f"\nMRR {rr_sum / len(QUERIES):.3f} — 참고값일 뿐 동등성 근거가 아니다 (ADR-0008 §2.6).")


if __name__ == "__main__":
    main()

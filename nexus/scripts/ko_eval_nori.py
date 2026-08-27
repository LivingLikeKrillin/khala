"""nori 를 **토크나이저로만** 쓴다 — 엔진도 스코러도 필터 정책도 바꾸지 않고
(SPEC-nexus-korean-retrieval-eval §4.4).

ADR-0008 §2.6 의 nori 탐색이 아무것도 증명하지 못한 첫째 이유는 **토크나이저와 함께 엔진이
바뀐 것**이었다(OpenSearch `match`+BM25 vs Postgres `to_tsquery`+`ts_rank_cd`). 여기서는 nori 를
`_analyze` API 로 **토큰만** 얻어 와서, 그 토큰을 우리의 `tokens_to_tsquery` · 우리의 tsvector ·
우리의 `ts_rank_cd` 에 그대로 넣는다. 남는 차이는 **분해**뿐이다.

둘째 이유가 될 뻔한 것은 **품사 필터**다. mecab 실험군은 `_INCLUDE_POS` 로 걸러지는데 nori 실험군이
안 걸러지면, 그 차이를 "분해 차이" 라고 부르게 된다. 그래서 `explain: true` 로 품사를 받아
**같은 allow-list 를 우리 코드에서** 적용한다(`nori_part_of_speech` stoptags 로 근사하지 않는다).
nori 와 mecab-ko 는 같은 mecab-ko-dic 태그셋을 쓰므로 이 비교가 성립한다.

띄우는 법 (탐색 실행 전용, CI 아님):

    docker run -d --name nori-eval -p 19200:9200 \
        -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true \
        opensearchproject/opensearch:2.17.1
    docker exec nori-eval bin/opensearch-plugin install --batch analysis-nori
    docker restart nori-eval
"""

from __future__ import annotations

import json
import urllib.request

from nexus.index.bm25 import _INCLUDE_POS

DEFAULT_URL = "http://localhost:19200"
DECOMPOUND_MODE = "mixed"       # 복합명사를 원형과 조각 둘 다 남긴다 — mecab allow-list 결과에 가장 가깝다


class NoriTokenizer:
    """`Tokenizer` 프로토콜 구현 — 하니스 전용. 프로덕션 경로에는 들어가지 않는다."""

    def __init__(self, url: str = DEFAULT_URL, decompound_mode: str = DECOMPOUND_MODE) -> None:
        self.url = url.rstrip("/")
        self.decompound_mode = decompound_mode
        self.id = f"nori-{decompound_mode}"
        self.policy = (f"nori(decompound_mode={decompound_mode}, user_dictionary=none) + "
                       f"POS allow-list {sorted(_INCLUDE_POS)} (mecab 실험군과 동일)")
        self.unknown_tags: dict[str, int] = {}     # allow-list 밖 태그 — 리포트에 그대로 적는다

    def analyze(self, text: str) -> list[tuple[str, str]]:
        """(토큰, 품사) 목록. 엔진 검색은 쓰지 않는다 — `_analyze` 만 쓴다."""
        body = json.dumps({
            "tokenizer": {"type": "nori_tokenizer", "decompound_mode": self.decompound_mode},
            "explain": True,
            "text": text,
        }).encode("utf-8")
        req = urllib.request.Request(f"{self.url}/_analyze", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:   # noqa: S310 — 로컬 상수 URL
            payload = json.loads(resp.read().decode("utf-8"))
        out = []
        for t in payload["detail"]["tokenizer"]["tokens"]:
            pos = (t.get("leftPOS") or t.get("posType") or "").split("(")[0].strip()
            out.append((t["token"], pos))
        return out

    def tokenize(self, text: str) -> list[str]:
        tokens = []
        for surface, pos in self.analyze(text):
            if pos in _INCLUDE_POS:
                tokens.append(surface.lower())
            elif pos:
                self.unknown_tags[pos] = self.unknown_tags.get(pos, 0) + 1
        return tokens

    def health(self) -> str:
        with urllib.request.urlopen(f"{self.url}/_cat/plugins", timeout=30) as resp:  # noqa: S310
            plugins = resp.read().decode("utf-8")
        if "nori" not in plugins.lower():
            raise RuntimeError("analysis-nori 플러그인이 없다 — 모듈 docstring 의 기동 절차를 보라")
        with urllib.request.urlopen(f"{self.url}", timeout=30) as resp:               # noqa: S310
            info = json.loads(resp.read().decode("utf-8"))
        return f"{info['version']['distribution']} {info['version']['number']} + analysis-nori"

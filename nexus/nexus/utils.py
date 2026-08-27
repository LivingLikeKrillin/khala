"""공용 유틸리티 함수.

get_search_text()는 검색/임베딩 텍스트 생성의 단일 경유점이다.
chunk_text를 직접 embedding이나 tsvector에 사용하지 말 것.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.models.chunk import Chunk


def context_prefix_for(title: str, section_path: str) -> str | None:
    """색인 접두사 — **문서 신원을 색인 텍스트에 넣는다** (A13 컷오버, 2026-08-26).

    `search_text` 는 `COALESCE(context_prefix, '[' || section_path || ']') || ' ' || chunk_text`
    다. `context_prefix` 가 NULL 이던 동안 접두사는 늘 섹션 경로였고, **섹션이 `root` 인 청크는
    자기가 무엇에 관한 것인지를 색인에 한 글자도 안 남겼다** — 라이브 `default` 에서 407 중 91.

    그 상태가 실제로 답을 막았다: 아바타 해금 임계값이 Notion DB 행마다 문서 하나로 들어와
    본문이 `- **디제잉 포인트**: 4000` 뿐이었고, 제목(`디제잉 아바타 10`)은 색인 밖이라
    "근거에 없습니다" 가 나왔다.

    **측정하고 넘어왔다** (`tests/eval/a13-round2/README.md`): 처치를 받는 질문에서 벡터
    Recall@10 0.444 → 0.889 (p=0.016), 대조군 24문항 Recall 1.000 → 1.000 (p=0.219).
    대조군의 순위는 소수에서 조금 나빠졌다 — 유의하지 않지만 비용으로 기록돼 있다.

    규칙(1·2회차 실험 실험군과 **같은 함수여야 한다** — 재면서 쓴 것과 배포되는 것이 갈리면
    그 측정은 아무 말도 안 한 것이 된다):

        섹션이 root/빈값     → `[제목]`
        제목이 섹션에 이미 있음 → `[섹션]`      (두 번 넣으면 신호가 흐려진다)
        그 외                → `[제목 > 섹션]`

    제목이 비면 `None` — 그때는 예전 동작(`[section_path]`)이 그대로 맞다.
    """
    section = (section_path or "root").strip()
    if not (title or "").strip():
        return None
    if section == "root" or not section:
        return f"[{title}]"
    if title in section:
        return f"[{section}]"
    return f"[{title} > {section}]"


def get_search_text(chunk: "Chunk") -> str:
    """청크의 검색/임베딩용 텍스트 생성.

    1.0: section_path 접두사를 붙여 context를 제공.
    2.0: context_prefix에 LLM Contextual Enrichment 결과를 넣으면
         이 함수 수정 없이 품질 향상.

    이 함수는 다음 2곳에서 사용된다:
    - index/bm25.py: tsvector 생성 시
    - index/embed.py: embedding 생성 시

    DB의 search_text GENERATED 컬럼도 동일한 로직:
    COALESCE(context_prefix, '[' || section_path || ']') || ' ' || chunk_text

    Args:
        chunk: Chunk 객체 (chunk_text, section_path, context_prefix 필요)

    Returns:
        검색/임베딩에 사용할 가공된 텍스트
    """
    from nexus.ingest.vision import strip_marker_line

    prefix = chunk.context_prefix or f"[{chunk.section_path}]"
    # 그림 추출 마커는 **기계용 손잡이**다(인용→원본 그림 왕복이 `chunk_text` 에서 파싱한다).
    # 색인에 넣을 이유가 없고, 넣으면 `derived`·`gemini`·`img`·해시가 토큰이 된다.
    body = strip_marker_line(chunk.chunk_text).strip()
    return f"{prefix} {body}"

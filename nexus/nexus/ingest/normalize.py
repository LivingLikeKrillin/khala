"""변경감지 해시용 본문 정규화(의미보존, 지터만 제거). 스펙 ⑥.

content_hash 를 raw 파일 전체가 아니라 이 함수를 거친 body 에서 계산해,
재익스포트 지터(타임스탬프는 frontmatter 로 제외 · CRLF · 행말공백)를
'변경'으로 오인하지 않게 한다. 소문자화·공백접기·마크다운 제거 같은
의미 훼손은 하지 않는다(거짓병합 방지).
"""

from __future__ import annotations


def normalize_for_hash(text: str) -> str:
    """개행 통일(CR/CRLF→LF) + 행말공백 제거 + 끝 빈 줄을 단일 개행으로.

    빈 입력(또는 공백/개행뿐)은 빈 문자열을 유지한다.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = "\n".join(line.rstrip() for line in normalized.split("\n"))
    body = stripped.rstrip("\n")
    return body + "\n" if body else ""

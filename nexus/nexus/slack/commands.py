"""봇에게 **봇 자신**을 묻는 자리 — 검색이 아니라 시스템 상태로 답한다.

2026-08-13 에 팀원이 슬랙에서 물었다: *"너가 근거로 사용 중인 corpus 범위는 어떻게 돼?"*
봇은 그것을 평범한 질문으로 받아 **검색**했고, 코퍼스를 논하는 설계 문서 다섯 건을 근거로
"이번 검색에서 Evidence 로 제공된 문서는 5개" 라고 답했다. 그건 코퍼스 범위가 아니라 그 턴의
근거 패킷이다. 실제 범위는 그 테넌트의 108건이었고, **시스템은 그 수를 이미 알고 있었다.**

자기 자신에 대한 질문을 검색으로 답하면, "그 주제를 다루는 문서" 가 뽑혀 그 산문이 시스템
상태인 것처럼 나간다. 근거가 붙어 있어 더 그럴듯하고, 그래서 더 나쁘다.

**분류하지 않는다.** "이건 메타 질문인가?" 를 모델이 판정하게 하는 설계는
`SPEC-nexus-multi-turn-narration` §3.2 에서 기각됐다 — 오분류가 양방향으로 안전하지 않기
때문이다. 여기서 쓰는 것은 **완전 일치**뿐이다: 메시지 전체가 짧은 명령어와 같을 때만 발동한다.
문자열 비교이므로 판정도, 잡음도, 오분류도 없다. 애매하면 평소대로 검색한다.
"""

from __future__ import annotations

#: 명령어 → 무엇을 보여줄지. **전체 일치만** 센다(부분 문자열이 아니다) — "corpus 설계가 뭐야"
#: 같은 진짜 질문이 명령으로 가로채이면, 고치기 전보다 나빠진다.
_SCOPE_WORDS = frozenset({
    "코퍼스", "corpus", "범위", "scope", "코퍼스 범위", "corpus 범위",
    "무슨 문서", "어떤 문서", "what documents",
})


def normalize(text: str) -> str:
    """비교용 정규화. 대소문자·앞뒤 공백·물음표만 없앤다 — 그 이상 손대면 일치가 느슨해진다."""
    return " ".join((text or "").strip().rstrip("?？!").split()).lower()


def is_scope_command(text: str) -> bool:
    """이 메시지가 **범위를 묻는 명령**인가. 완전 일치만."""
    return normalize(text) in {normalize(w) for w in _SCOPE_WORDS}


#: 출처 코드 → 사람이 아는 말. 코드 이름(`notion`)은 시스템의 어휘이지 팀원의 어휘가 아니다.
_SOURCE_LABEL = {"notion": "Notion", "git": "Git 저장소", "other": "기타"}


#: 명령어("코퍼스") 응답의 첫 줄.
LEAD_COMMAND = "*답변 근거는 {src} 입니다.* 검색 결과가 아니라 시스템 상태입니다."
#: 근거를 하나도 못 잡았을 때의 첫 줄. **같은 카드, 다른 말문**이다 —
#: 카드를 하나 더 만들면 코퍼스가 바뀌는 날 한쪽만 낡는다.
LEAD_MISS = "*이 질문은 제가 가진 문서 밖입니다.* 대신 제가 아는 것은 {src} 입니다."


def scope_note(vis: dict) -> str:
    """한 줄짜리 꼬리표. 근거는 잡혔지만 **잘 안 맞을 때** 쓴다.

    그때는 근거 문서 제목이 **이미 화면에 있다**(`formatter.format_answer` 가 최대 5건을
    그린다). 그 위에 카드를 펼치면 같은 말을 두 번 하는 것이고, 빠진 것은 하나뿐이다 —
    *이 코퍼스가 대체 무엇을 담고 있나*. 그래서 한 줄만 준다.

    값이 없으면 빈 문자열(= 아무것도 안 붙인다). 진단 실패가 답변을 어지럽히지 않는다.
    """
    visible = vis.get("documents_visible") or 0
    if not visible:
        return ""
    src = _sources_phrase(vis)
    newest = (vis.get("newest_document_at") or "")[:10]
    tail = f" · {newest} 까지" if newest else ""
    return f"제가 가진 것은 {src}{tail} 입니다. 그 밖의 것은 모릅니다."


def _sources_phrase(vis: dict) -> str:
    """"Notion 108건" 같은 구절. 출처도 개수도 **코퍼스 자신에서** 온다."""
    sources = vis.get("sources") or {}
    if not sources:
        return f"문서 {vis.get('documents_visible') or 0}건"
    return " · ".join(f"{_SOURCE_LABEL.get(k, k)} {n}건" for k, n in sources.items())


def scope_blocks(vis: dict, *, lead: str = "") -> list[dict]:
    """`/visibility` 응답 → 슬랙 블록.

    `lead` 는 첫 줄만 바꾼다(기본 = 명령어 응답). 본문은 **한 벌뿐**이다 — 부르는 자리가
    늘어난다고 카드를 복제하지 않는다.

    **팀원의 질문에 답한다.** "코퍼스 범위가 어떻게 돼?" 를 물은 사람이 알고 싶은 것은
    *"내가 뭘 물어봐도 되냐"* 이지 문서 개수가 아니다. 첫 판은 테넌트 이름과 열람 등급을 앞에
    내세웠는데, 그 둘은 **시스템의 어휘이지 팀원의 어휘가 아니다** — `default` 도 `INTERNAL` 도
    묻는 사람에게 아무 뜻이 없다. 그래서 순서를 바꿨다: 어디서 왔나 → 무엇에 대한 것인가 →
    얼마나 최신인가. 등급은 **불일치가 있을 때만** 나온다(그때는 뜻이 생긴다).

    설명문은 손으로 쓰지 않는다. 출처도 예시 제목도 **코퍼스 자신에서** 온다 — 손으로 쓴 소개는
    코퍼스가 바뀌는 날부터 거짓말을 시작한다.

    **이 카드는 검색 결과가 아니다.** 근거도 인용도 없고, 대신 그 사실을 말한다.
    """
    visible = vis.get("documents_visible") or 0
    total = vis.get("documents_total") or 0
    newest = (vis.get("newest_document_at") or "")[:10]
    titles = vis.get("sample_titles") or []

    if not visible:
        return [{"type": "section", "text": {"type": "mrkdwn", "text":
                 "*답변 근거로 쓸 수 있는 문서가 없습니다.*\n"
                 f"이 봇의 열람 등급으로 보이는 문서가 0건입니다"
                 f"{f' (전체 {total}건 중)' if total else ''} — 운영자에게 알리세요."}}]

    lines = [(lead or LEAD_COMMAND).format(src=_sources_phrase(vis)), ""]
    if titles:
        lines.append("이런 문서들입니다:")
        lines += [f"  • {t}" for t in titles[:5]]
        lines.append("")
    if newest:
        lines.append(f"가장 최근 갱신: *{newest}*  ·  총 *{visible}건*")
    else:
        lines.append(f"총 *{visible}건*")
    if total != visible:
        # 이 차이는 모르면 "코퍼스에 없다" 로 오해된다. 없는 게 아니라 **안 보이는** 것이다.
        lines.append(f"열람 등급 때문에 {total - visible}건은 이 봇에게 보이지 않습니다.")
    lines += [
        "",
        "_이 목록 밖의 것(코드, 이슈, 슬랙 대화, 갱신일 이후의 변경)은 모릅니다._",
    ]
    return [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]

"""👍/👎 버튼과 그 클릭 처리 (SPEC-nexus-answer-feedback U2, approved 2026-08-14, 안 B).

**👎 는 지표가 아니라 단서다.** 이 표면이 하는 일은 셋이다: 답변에 버튼 둘을 붙이고, 👎 면
사유 넷을 **ephemeral 로** 되묻고, 운영자에게 **한 번** DM 한다.

**아무 데도 알리지 않는다** (§3.7, 2026-08-14 개정). 초안은 👎 를 운영자에게 DM 으로 밀었다.
월 10표짜리 신호에 푸시는 과하고, 무엇보다 그 요구사항은 "건별로 정보가 있다" 를 "도착 즉시
본다" 로 오독한 데서 나왔다. 자료는 쌓이고 `nexus feedback` 이 주기적으로 뽑는다 — 요구사항
하나를 지우니 아웃바운드 경로·`im:write`·앱 재설치·중복억제 상태가 같이 사라졌다.

**공개 표시도 하지 않는다.** 봇은 `thread_ts` 로 채널 스레드에 답하므로 깃발이 공개로 꽂히면
5명 팀에서 그 스레드의 질문자가 사실상 지목된다 — 스키마와 로그에서 지운 연결을 **슬랙 UI 가
공개로 복원**하는 것이다.

**사용자 id 는 어디에도 안 남는다.** `block_actions` 페이로드는 `answer_key` 와 사용자 id 를
같은 객체에 담아 오므로, 여기서 페이로드를 통째로 찍는 로그 한 줄이면 §3.4 가 스키마에서
지운 투표자↔답변 연결이 로그에 되살아난다.
"""

from __future__ import annotations

import logging
import os
import secrets

import httpx

logger = logging.getLogger(__name__)

#: **봇은 DB 에 안 붙는다.** 읽기 전용 principal 토큰 하나만 들고 nexus 에 HTTP 로 말한다 —
#: 저장 층은 서버 쪽에 있고 테넌트는 그 principal 이 정한다(`effective_scope`). 봇에
#: `DATABASE_URL` 을 주는 것이 한 줄 더 싸지만, 그러면 등급·격리를 우회해 모든 문서를 읽을 수
#: 있게 되고 그 토큰을 읽기 전용으로 묶어 둔 이유가 사라진다.
NEXUS_API_URL = os.getenv("NEXUS_API_URL", "http://localhost:8000")
NEXUS_SLACK_TOKEN = os.getenv("NEXUS_SLACK_TOKEN", "")


class VoteRefused(Exception):
    """서버가 이 투표를 거절했다(결속 불일치·만료). 409 로 온다."""


async def _post(path: str, payload: dict) -> dict:
    """nexus 로 한 번. 실패는 예외로 올린다 — 호출부가 사용자에게 무엇을 말할지 정한다."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{NEXUS_API_URL}{path}", json=payload,
                              headers={"Authorization": f"Bearer {NEXUS_SLACK_TOKEN}"})
    if r.status_code == 409:
        raise VoteRefused(r.json().get("detail", "거절됨"))
    r.raise_for_status()
    return r.json().get("data", {}) or {}

#: 답변에 붙는 근거 개수의 상한. `formatter` 가 `[:5]` 로 자르므로 블록 수가 그 위로 안 간다 —
#: I8 의 "최대 개수" 를 이름으로 고정한다(안 그러면 예산 검사가 임의 표본이 된다).
EVIDENCE_CEILING = 5

ACTION_UP, ACTION_DOWN, ACTION_REASON = "fb_up", "fb_down", "fb_reason"

#: 사유 코드. **서버 스키마의 CHECK 와 같은 목록**이어야 한다 (`nexus/feedback/store.py`).
#: 여기 두는 이유: 봇은 저장 층을 import 하지 않는다 — import 하면 그 모듈이 `nexus.db` 를
#: 끌고 오고, 봇 프로세스에 DB 가 있는 것처럼 보이는 코드가 된다(실제로 없다).
REASONS = ("wrong_evidence", "not_my_question", "ignored_format", "not_found")


def issue_key() -> str:
    """답변 하나에 붙는 불투명 키. 128비트 CSPRNG — 버튼 페이로드로 나가므로 보안 파라미터다."""
    return secrets.token_urlsafe(16)


async def record_offer(*, answer_key: str, channel_id: str, message_ts: str,
                       answer_text: str = "") -> None:
    """제안 한 줄(분모). **best-effort** — 답변은 이미 나갔고 여기서 예외를 올리지 않는다."""
    try:
        await _post("/feedback/offer", {"answer_key": answer_key,
                                        "channel_id": channel_id, "message_ts": message_ts,
                                        # **보여 준 답변 원문.** 신고가 오면 그 답에
                                        # 대 봐야 한다 — 없으면 진단이 시작도 못 한다.
                                        "answer_text": answer_text})
    except Exception as exc:  # noqa: BLE001
        logger.warning("feedback offer failed: %s", type(exc).__name__)

#: 버튼 옆 한 줄 = 고지 (§3.6). 문구를 바꾸면 `store.NOTICE_VERSION` 도 올린다 —
#: 나중에 "그때 무엇을 보여줬나" 에 답할 수 있어야 한다.
NOTICE = "이 평가는 답변 품질 개선에만 쓰입니다. 누가 눌렀는지는 기록하지 않습니다."

_REASON_LABELS = {
    "wrong_evidence": "근거가 틀렸다",
    "not_my_question": "내 질문이 아니다",
    "ignored_format": "형식을 무시했다",
    "not_found": "못 찾았다",
}

def _texts(block: dict) -> list[str]:
    """블록 안의 모든 텍스트 문자열. 예산 검사가 **모든 자리**를 지나게 한다."""
    out: list[str] = []
    t = block.get("text")
    if isinstance(t, dict) and isinstance(t.get("text"), str):
        out.append(t["text"])
    for el in block.get("elements", []) or []:
        if isinstance(el, dict):
            out.extend(_texts(el))
            if isinstance(el.get("text"), str):
                out.append(el["text"])
    return out


def feedback_blocks(answer_key: str) -> list[dict]:
    """답변 뒤에 붙는 블록 둘: 버튼 행 + 고지 한 줄."""
    return [
        {
            "type": "actions",
            "elements": [
                {"type": "button", "action_id": ACTION_UP, "value": answer_key,
                 "text": {"type": "plain_text", "text": "👍 도움됐다"}},
                {"type": "button", "action_id": ACTION_DOWN, "value": answer_key,
                 "text": {"type": "plain_text", "text": "👎 아니다"}},
            ],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": NOTICE}]},
    ]


def reason_blocks(vote_id: str) -> list[dict]:
    """👎 뒤 되묻는 사유 넷. **투표 행 id 를 value 에 실어** 되돌려받는다.

    `answer_key` 로 찾으면 안 된다 — 한 답변에 여러 사람이 투표하므로 후보가 여럿이고,
    잘못 고르면 남의 투표에 내 사유가 적힌다. 사유는 이 기능의 유일한 산출물이다.
    """
    return [
        {"type": "section",
         "text": {"type": "mrkdwn", "text": "무엇이 잘못됐나요? (선택 안 해도 됩니다)"}},
        {"type": "actions",
         "elements": [
             {"type": "button", "action_id": f"{ACTION_REASON}_{code}",
              "value": f"{vote_id}:{code}",
              "text": {"type": "plain_text", "text": label}}
             for code, label in _REASON_LABELS.items()
         ]},
    ]


async def _say(client, channel: str, user: str, text: str, blocks=None) -> None:
    """당사자에게만 보이는 답. 원 답변 메시지는 고치지 않는다 (§3.1.1)."""
    try:
        await client.chat_postEphemeral(channel=channel, user=user, text=text,
                                        **({"blocks": blocks} if blocks else {}))
    except Exception as exc:  # noqa: BLE001 — 안내 실패가 투표를 되돌리지 않는다
        logger.warning("feedback ephemeral failed: %s", type(exc).__name__)


async def on_vote(body: dict, client) -> None:
    """👍/👎 클릭. **예외를 밖으로 내보내지 않는다** (§4 I6).

    로그에 페이로드를 통째로 찍지 않는다 — 사용자 id 가 거기 들어 있다 (§4 I4).
    """
    action = body["actions"][0]
    answer_key = action["value"]
    channel = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    user = body["user"]["id"]          # ephemeral 을 보내는 데만 쓰고, 저장·로그하지 않는다
    verdict = "up" if action["action_id"] == ACTION_UP else "down"

    try:
        vote_id = (await _post("/feedback/vote", {
            "answer_key": answer_key, "verdict": verdict,
            "channel_id": channel, "message_ts": message_ts}))["vote_id"]
    except VoteRefused as exc:
        await _say(client, channel, user,
                   f"이 평가는 받을 수 없습니다 ({exc}). 새 질문에 다시 눌러 주세요.")
        return
    except Exception as exc:  # noqa: BLE001 — 피드백이 답변 경로를 죽이면 안 된다
        # **예외 문구를 그대로 찍지 않는다.** 밑단이 무엇을 담아 올릴지 우리가 정하지 못하고,
        # 실제로 키가 섞여 나왔다(I13 검사가 잡았다). 종류만 남기고 상세는 store 의 로그가
        # 갖는다 — 거기엔 키가 없다.
        logger.warning("feedback vote failed: %s", type(exc).__name__)
        await _say(client, channel, user, "평가를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    if verdict == "up":
        await _say(client, channel, user, "고맙습니다.")
        return

    await _say(client, channel, user, "고맙습니다. 무엇이 잘못됐나요?",
               blocks=reason_blocks(vote_id))


async def on_reason(body: dict, client) -> None:
    """사유 버튼 클릭. 가드에 걸리면 **조용히 무시하지 않고 사용자에게 알린다.**"""
    channel = body["channel"]["id"]
    user = body["user"]["id"]
    try:
        vote_id, reason = body["actions"][0]["value"].split(":", 1)
        ok = (await _post("/feedback/reason",
                          {"vote_id": vote_id, "reason": reason}))["applied"]
    except Exception as exc:  # noqa: BLE001 — 같은 이유로 종류만 (I13)
        logger.warning("feedback reason failed: %s", type(exc).__name__)
        await _say(client, channel, user, "사유를 저장하지 못했습니다.")
        return

    await _say(client, channel, user,
               "기록했습니다. 고맙습니다." if ok
               else "이미 사유가 기록됐거나 시간이 지났습니다.")

-- 036: **보여 준 답변을 남긴다.**
--
-- **무엇이 막혔나 (2026-08-30, 파일럿 첫날).** 사용자가 슬랙에서 받은 답이 이상하다고
-- 말했다 — *"두 가지입니다"* 로 시작해 놓고 하나만 있었다. 그 답을 꺼내 보려 했더니
-- **어디에도 없었다.** 질문 원문은 남는데(017) 답변은 안 남는다. `answer_offered` 가
-- 가진 것은 해시와 채널·타임스탬프뿐이라, 👎 를 눌러도 무엇이 나빴는지 볼 수가 없다.
--
-- 그 자리에서 진단이 멈췄다. 내가 같은 질문을 다시 돌리면 653자짜리와 2,000자짜리가
-- 나왔고, 사용자가 본 것은 150자였다. **셋이 같은 답인지 다른 답인지 알 방법이 없다.**
--
-- **키는 `answer_key` 그대로다.** 017 은 principal 과 이어붙지 못하게 소금 친 키를 썼는데,
-- 여기서는 목적이 반대다 — 이 표는 **투표와 이어져야** 쓸모가 있다. `answer_vote` 가 이미
-- `answer_key` 로 서 있으므로 같은 키를 쓴다.
--
-- ⚠ **고지는 아직 질문만 말한다.** 2026-08-14 팀 공지는 질문 보존을 알렸고 답변 보존은
-- 언급하지 않는다. 소유자가 그 문구를 갱신할 때까지 이 표의 존재는 OPEN.md 에 사람 몫으로
-- 서 있다.

CREATE TABLE IF NOT EXISTS search_answer_text (
    tenant      text        NOT NULL,
    -- `answer_offered`·`answer_vote` 와 같은 키. 투표를 답변에 붙이는 것이 이 표의 목적이다.
    answer_key  text        NOT NULL,
    answer_text text        NOT NULL,
    -- 길이를 따로 둔다. 회차마다 답변 길이가 크게 흔들리는 것이 첫날의 관측이었고,
    -- 그 흔들림은 본문을 다 읽지 않고도 한 줄로 보여야 한다.
    chars       integer     NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, answer_key)
);

COMMENT ON TABLE search_answer_text IS
    '사람에게 실제로 보여 준 답변. 신고를 그 답에 대 보려면 답이 남아 있어야 한다.';

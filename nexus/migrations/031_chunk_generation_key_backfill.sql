-- 031: 청크의 **세대 키**를 문서에 맞춰 되돌린다 (`chunks.hash` = `documents.content_hash`).
--
-- **왜.** `revive()` 와 `unsupersede()` 는 "현재 세대만 되살린다" 를
-- `chunks.hash = (SELECT content_hash FROM documents …)` 로 표현한다(`nexus/lifecycle.py`).
-- 그 등식이 성립한다는 근거로 docstring 이 든 것은 *"pipeline.py 가 같은 값으로 둘 다 쓴다"*
-- 인데, 쓰지 않았다: `_save_document` 의 ON CONFLICT 는 `content_hash` 를 갱신하고
-- `_save_chunks` 의 ON CONFLICT 는 `hash` 를 갱신하지 않았다. 그래서 **한 번이라도 편집되어
-- 재적재된 문서는 두 값이 갈라진 채로 앉아 있다.**
--
-- **무엇이 실제로 망가졌나.** 갈라진 문서가 soft_delete → revive 를 거치면 문서만 `active` 로
-- 서고 청크는 0건 되살아난다. 그 결과가 유령 문서다: 목록·개수·커버리지에는 건강하게 보이는데
-- (커버리지의 모집단은 *청크*라 청크 0건인 문서는 분모에도 없다) 어떤 다리도 읽지 못한다.
-- 라이브 `default` 에서 `SLACK_BOT.md` 가 정확히 그렇게 됐고, 같은 코퍼스의 Notion 문서 8건
-- (활성 청크 84개)이 같은 상태로 대기 중이었다. 방아쇠는 사람 명령이 아니라 자동 작업이다 —
-- `ingest-notion --reconcile` 이 사라진 페이지를 내리고 돌아온 페이지를 revive 한다.
--
-- **왜 이 백필이 안전한가.** `_save_chunks` 는 새 청크를 쓰기 전에 그 문서의 **활성 청크를 전부
-- superseded 로 내린다.** 따라서 *active 문서 아래의 active 청크* = 마지막 적재의 산출물 =
-- 현재 세대다. 이 UPDATE 는 고쳐진 파이프라인이 그때 썼어야 할 값을 그대로 쓴다.
--
-- **건드리지 않는 것:** non-active 문서 아래의 청크와 superseded 청크. 그들의 옛 해시는 옛
-- 세대를 가리키는 참값이고, revive 가 그것을 되살리지 않는 것이 바로 의도다.
--
-- ⚠ 이 백필은 **이미 유령이 된 문서를 되살리지 않는다.** 그 문서에는 active 청크가 0건이라
-- 여기서 걸릴 행이 없다. 되살리는 방법은 재적재뿐이고(청크 텍스트가 낡았을 수 있다),
-- `nexus status` 가 이제 그 문서를 이름으로 지목한다(`fetch_unreachable_documents`).

UPDATE chunks c
   SET hash = d.content_hash,
       updated_at = now()
  FROM documents d
 WHERE c.doc_rid = d.rid
   AND d.status = 'active'
   AND c.status = 'active'
   AND c.hash <> d.content_hash;

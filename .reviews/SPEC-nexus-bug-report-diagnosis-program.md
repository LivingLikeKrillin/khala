---
target: SPEC-nexus-bug-report-diagnosis-program
critiqued_hash: sha256:376a031982e3bbc0b28fbba35e71633b771d36966d66cd112ea7308cdcb6730f
critiqued_at: '2026-09-23T11:32:32Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: U4(§4.5)는 판독 텍스트를 질문 시점에 만들어 근거 꾸러미에 바로 넣는다. ADR-0010 §6 은 「추출이 스캔에
    선행한다 — 추출 결과가 ingest/scanner.py 와 격리 게이트를 다른 문서 내용과 같은 조건으로 통과해야 한다」를 불변식으로 못박았고,
    그 근거로 '픽셀에만 보이는 업무 이메일'을 들었다. SPEC 은 U1 적재 경로의 PII 게이트만 언급하고 U4 경로에는 스캐너가 없다.
    카카오톡 오픈채팅 스크린샷은 정확히 사람 식별자가 픽셀에 있는 부류다.
  status: open
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: 판독을 '브리지 opus 신원'으로 부른다(§4.5). 키리스 브리지는 Claude Code 자식 프로세스이므로 판독기가
    파일시스템·도구를 가진다. ADR-0010 §6 은 「판독기는 도구도 파일시스템도 없다 · 이미지 바이트를 받아 텍스트를 돌려줄 뿐」을 §6
    순서(스캔 전 판독)의 '대가'로 명시했고, 파일 접근이 있는 판독기는 격리 게이트 앞에 놓인 파일 유출 프리미티브라고 적었다. SPEC 은
    이 제약을 인용도 충족도 하지 않는다.
  status: open
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: §4.5 는 판독 조각을 'machine_read 등급(ADR-0010 hop 3)'이라고만 적는다. ADR-0010 §4
    는 여섯 홉(청킹·SearchHit·근거 꾸러미/프롬프트·인용·API 응답·MCP 결과) 전부에서 등급이 살아남아야 적합하며 홉 하나라도 벗겨지면
    '추출 안 하느니만 못하다'고 규정하고, §7 은 그 전에 어떤 코퍼스에도 추출을 들이지 말라고 한다. 인용(hop 4)·`/search/answer`
    응답(hop 5)·MCP(hop 6)에서 이 조각의 등급이 어떻게 실리는지 SPEC 에 없다.
  status: open
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: 판독 결과를 저장하지 않으므로(§4.5) ADR-0010 §3.1 이 요구한 두 동반 필드 — 판독기 신원(`{model}/{prompt_sha}`)과
    재해결 가능한 출처 참조(source URI+block id+바이트 해시) — 가 지속 기록으로 남지 않는다. ADR-0010 §2 가 machine_read
    의 유일한 회수 수단으로 정한 '원본에서 이미지를 다시 읽는다'가 성립하지 않고, 분쟁 문장이 어느 판독기에서 나왔는지 사후에 열거할 수 없다.
    '판독기 신원 기록'이라는 한 구절은 어디에 어떤 수명으로 남는지 정의되지 않았다.
  status: open
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: high
  description: '''보존 경로에는 판독 텍스트를 넣지 않는다''(§4.5)는 판독 텍스트 자체만 막는다. 그런데 그 텍스트는 프롬프트에
    들어가 답변·인용으로 재생산되고, 답변은 저장된다(§4.6 이 ''최근 7일 답변 486건''을 세는 것이 그 증거다). 채팅 이름·업무 이메일이
    답변 산문·인용 스니펫을 통해 보존 표에 남는 경로가 닫혀 있지 않다. 완료 조건 ''판독 텍스트가 보존 표에 없음''(§7)도 어느 표를
    어떻게 검사하는지 정의하지 않아 이 누출을 통과시킨다.'
  status: open
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: high
  description: 'U1(§4.2)이 이슈 하나 = 문서 하나를 만들면서 문서 식별자 규칙을 정하지 않았다. ADR-0006 은 문서 정체성이
    `canonical_uri = "{tenant}:{filename}"`(basename)이며 이것이 ''너무 거칠어 서로 다른 문서가 같은
    basename 으로 조용히 덮어쓴다''를 Slice 1 의 알려진 한계로 기록했다. 리포가 둘(platform·web)이고 번호가 겹치므로(예:
    376) 파일명 규칙 없이는 한쪽 이슈가 다른 쪽을 말없이 지운다. 완료 조건 ''이슈 ≥ 50 적재''는 덮어쓰기가 나도 참일 수 있어 이
    결함을 잡지 못한다.'
  status: open
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: high
  description: §4.4 는 `code_source.repo_path` 를 목록으로 바꾸고 `CodeValueResolver` 가 '리포
    목록을 순회한다'고만 적는다. 같은 심볼/필드 이름이 백엔드와 프론트 양쪽에서 잡힐 때의 해결 순서·중복 시 거부 여부·claim 의 `value_source`
    가 어느 리포를 가리키는지가 정의되지 않았다. ADR-0004 §2 는 Archon 의 가치가 '현재 강제되는 값 + 권위 + 드리프트 경고'라고
    못박았으므로, 첫 매치 승리로 조용히 다른 리포의 값이 잡히면 드리프트 해시가 엉뚱한 심볼에 묶여 권위 신호 자체가 거짓이 된다. §8 이
    앵커 표의 리포 식별자 부재는 인정하면서 같은 문제를 안은 값 해석기는 게이트 조각으로 진행시킨다.
  status: open
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: high
  description: §4.4 의 새 값 모양 셋(JSX `maxLength={N}` · zod `.max/.min` · i18n 키)을 '1차는
    정규식 + 파일 한정자'로 읽는다. 이 결과는 ADR-0004 가 '결정-등급 사실 확인'으로 규정한 live code constant 등급으로
    흘러들어가고 claim `ruled_value` 의 후보가 된다. 정규식이 조건부 값·변수 참조·스프레드·상수 재수출·동적 스키마를 잘못 읽으면
    '지금 강제되는 값'이라는 최고 권위 표찰을 단 틀린 값이 나간다. 오탐·미탐 상한이나 파서가 확신 못 할 때 기권하는 규칙이 없다.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: adr-contradiction
  severity: medium
  description: 결정 5 가 '이 서비스를 호출하는 사람이 없다'를 자인하면서 다섯 조각(그중 셋은 게이트 대상)을 착수한다. ADR-0002
    는 각 부채-서비스 기능을 '이 부채가 실제로 쌓이는가, 신호를 보여라'에 게이트하고 그 규율이 A2A 를 멈춰 세웠다고 적었으며, ADR-0004
    의 '정직한 상태' 절은 남은 질문이 중복이 아니라 수요라고 못박았다. SPEC 은 이 게이트가 어떤 관측된 신호로 발화했는지(ADR-0002
    가 '방향의 첫 기록물에 적으라'고 요구한 항목)를 적지 않는다. 관측된 제보는 1건이다.
  status: open
  disposition_reason: null
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: 라벨 재료 수가 문서 안에서 갈린다. §2 표는 '원인이 코퍼스에 문서화된 것 61 중 3', §4.2 는 '원인 절이
    달린 이슈 60건', §4.1 은 '확정 원인이 적힌 것만 라벨' + Cleric 의 200 중 12(6%) 수율을 인용하면서 첫 목표를 20건으로
    잡는다. 6% 수율이 맞으면 60건에서 나오는 라벨은 한 자릿수이고, 60건 전부에 쓸 만한 원인 절이 있다면 '61 중 3' 과 어긋난다.
    어느 쪽이든 U0(다른 모든 조각의 측정 전제)의 20건 목표가 근거 없이 서 있다.
  status: open
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: §4.2 가 '댓글은 1차 제외(원인 절은 본문에 있다)'를 근거 없이 단정한다. 실제 조사에서 원인은 흔히 논의 끝 댓글·연결된
    PR 에서 확정되고, §2 의 분류 자체가 '이슈 본문의 원인 절 기준, 내 판단'이었다. 본문만 넣고 원인이 댓글에 있는 이슈들은 '적재했는데도
    답이 안 나온다'로 나타나 U1 완료 조건(정확 ≥ 5)의 실패 원인을 잘못 귀속시킨다.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: 닫힌 이슈는 '그때 그 말'인데(§4.2 가 인정) supersession·신선도 정책이 없다. 고쳐진 버그의 증상·원인
    절이 `documents.status='active'` 로 무기한 남아 ADR-0006 이 1위 엔트로피 실패 모드로 규정한 버전 공존을 60건
    규모로 늘린다(정규화 제목 어간 충돌 신호 ③도 함께 튄다). '프롬프트 규칙 6·7 이 상충을 밝힌다'는 산문 완화일 뿐 결정론적 봉쇄가
    아니며, `exclude_doc_types` 는 기본이 포함이라 설계 별칭 소비자는 옵트아웃하지 않는 한 옛 증상을 근거로 받는다.
  status: open
  disposition_reason: null
- issue_id: I-013
  category: missing-invariant
  severity: medium
  description: §4.6 은 유일한 공유 자원이 키리스 브리지(동시 한도 1, 5초 대기 뒤 503)라고 하고 'U2 는 브리지를 안 쓴다'로
    안심하지만, U4 는 질문 시점마다 브리지로 판독을 부른다(§4.5). 설명 층 답변과 판독이 같은 한도를 다투는데 점유 시간(실측 6.0s/11.4s)·503
    시 요청의 실패 모드·부분 답변 여부가 정의되지 않았고, 완료 조건의 '브리지 호출 0' 검사는 U2 에만 걸려 있다. 전체 조건의 'picasso
    지연 불변'은 U4 가 라이브로 돌기 전에는 발동하지 않는다.
  status: open
  disposition_reason: null
- issue_id: I-014
  category: untestable-requirement
  severity: medium
  description: U3 완료 조건 '나머지 슬라이스 오탐 0(사람 확인)'은 슬라이스의 범위(필드 수·표면 수), 표본 크기, 확인자, 오탐의
    정의가 모두 없어 판정할 수 없다. 프론트 리포 전체에서 오탐 0 을 사람이 확인한다는 뜻이라면 수행 불가능하고, 몇 건만 본다는 뜻이라면
    결과를 보기 전에 고정하라는 §7 의 자기 규칙을 어긴다.
  status: open
  disposition_reason: null
- issue_id: I-015
  category: untestable-requirement
  severity: medium
  description: §6 의 4단계 '측정 — 2~4주, 실제 제보로 R1~R5' 에 완료 조건이 없다(§7 은 U0~U4 만 정의). 필요한
    제보 수, 미달 시 행동(연장인지 중단인지), 무엇이 이 단계를 통과시키는지가 비어 있다. 관측된 실제 제보는 1건이고 유입률은 어디에도 측정돼
    있지 않아, 2~4주가 0~2건으로 끝날 때 다음 조각(U3·U4)으로 갈지 말지가 결정 불가 상태로 남는다.
  status: open
  disposition_reason: null
- issue_id: I-016
  category: unverifiable-claim
  severity: medium
  description: §2 의 '두 번 읽어 변동 0.0' 을 판독기 신뢰 근거로 U4 에 쓴다. 표본은 한 쌍(n=1)이고 이미지 종류·판독기
    잡음 바닥이 측정되지 않았다. ADR-0010 §5 가 '같은 이미지 재실행이 한 글자 단위로 흔들린다'를 전제로 삼은 것과도 어긋나며, 같은
    값 하나로 '저장 안 하니 §5 는 무관하다'는 결론까지 지탱하고 있다.
  status: open
  disposition_reason: null
- issue_id: I-017
  category: unverifiable-claim
  severity: medium
  description: §6 의 비용 문단이 검증 불가한 수 셋에 기대고 있다. ①'개발 중 지출은 키리스라 0' — U0 채점이 브리지를 쓰고
    3회 다수결 × 20 라벨이므로 실행 가능성(동시 한도 1, 건당 4~7분 직렬)과 지출 경로가 함께 확인돼야 한다. ②'월 30건'은 관측이
    아니라 가정이다(실측 제보 1건). ③'제 작업 2~3주'는 게이트 대기 시간과 4단계의 2~4주를 포함하는지 불명이다.
  status: open
  disposition_reason: null
- issue_id: I-018
  category: undefined
  severity: medium
  description: R5(판정 존중)가 'claim 판정이 있으면 되묻지 않고 판정값으로 답' 인데, 자유 텍스트 제보에서 해당 claim
    을 어떤 규칙으로 찾는지 정의되지 않았다. §5 는 claim 매칭의 형태소 확장 금지(2026-09-03 결정)를 유지하므로, 스크린샷에서
    온 구어체 제보가 claim 표현과 어휘가 어긋나면 판정이 있어도 붙지 않는다. 그 경우 R5 는 시스템이 아니라 제보 문구를 채점하게 되고,
    U0 라벨의 'claim id' 칸은 채점에 쓰일 길이 없다.
  status: open
  disposition_reason: null
- issue_id: I-019
  category: risky-assumption
  severity: medium
  description: U2 목표 'R1 방향 ≥ 12/20' 을 코드 읽는 에이전트 4건(3건 방향 일치, 1건은 이슈 기록과 반대 결론)과
    무힌트 2/2 에서 끌어왔다. n=4·n=2 는 60% 선을 정할 근거가 못 되고, 4건 중 하나가 반대 결론이었다는 사실은 표본 내 실패율이
    이미 25% 임을 뜻한다. 또한 이 네 건은 원인이 이미 알려진 사례였을 가능성이 배제돼 있지 않다(프로브에서 정확했던 3건이 전부 그런 경우였다).
  status: open
  disposition_reason: null
- issue_id: I-020
  category: scope-creep
  severity: low
  description: '`nexus code parity` 는 khala 안에 새 정적 분석 CLI(어법 표 유지보수 포함)를 만든다. ADR-0004
    는 컴포넌트 경계를 ''접지 원천의 분업''으로 정의하고 Probe 를 다중 원천 증거(플랫폼 정합성·계약 린트)의 자리로 두었으며, Nexus
    는 문서 색인 · Archon 은 질의 시점 live constant 로 한정했다. 짝 대조는 두 코드 지점의 정합성 검사라 Probe 쪽
    접지에 가깝고, khala 에 두면 어법 표라는 영구 유지보수 표면이 붙는다. 어느 컴포넌트가 소유하는지에 대한 판단이 문서에 없다.'
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---


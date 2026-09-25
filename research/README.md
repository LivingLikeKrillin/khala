# research — 밖에서 같은 문제를 어떻게 푸는가

이 디렉터리는 **다른 조직의 실태 조사**를 담는다. SPEC 도 ADR 도 아니다 — 우리가 무엇을
할지 정하는 문서가 아니라, **정하기 전에 밖을 본 기록**이다.

**왜 있나.** 이 리포는 `research-before-rederiving-known-rag` 라는 규칙을 갖고 있다 —
*"RAG 난제는 대개 이미 풀려 있다. 재발명하지 말고 조사부터 하라."* 그런데 그 규칙은
지금까지 **기법 층**에만 적용됐다. 조직 지식 시스템을 몇 달 만들면서 *다른 조직이 이
문제를 어떻게 푸는가* 를 한 번도 정리한 적이 없다. 이 디렉터리가 그 자리다.

**규칙 셋.**

1. **한계를 맨 앞에 적는다.** 조사는 공개 자료로만 하고, 공개 자료는 성공한 것만 글이 된다.
   그 편향을 문서가 스스로 말하지 않으면 읽는 사람이 못 가른다.
2. **벤더 자료는 벤더 자료라고 표시한다.** 이해관계자의 진술은 근거이되 등급이 다르다.
3. **수치에는 누가 보고한 것인지 붙인다.** 이 문서들의 숫자는 거의 전부 회사 자기 보고이고
   독립 검증된 것이 아니다.

| 문서 | 무엇 |
|---|---|
| [`2026-09-04-org-knowledge-systems.md`](2026-09-04-org-knowledge-systems.md) | AI 도구를 적극 쓰는 회사들이 공용 지식 베이스를 어떻게 구축·운용·소비하는가 |
| [`2026-09-04-rag-current-practice.md`](2026-09-04-rag-current-practice.md) | RAG 현행 관행 정본 — 층 구조·실패 귀속·평가·부패·코퍼스·문서 타입·도구. khala 대조의 기준선 |
| [`2026-09-04-representation-in-ai-assisted-development.md`](2026-09-04-representation-in-ai-assisted-development.md) | AI 를 쓰는 개발에서 담당자의 시스템 모델은 어떻게 되는가 — 문헌·실측치와 그로부터 끌어낸 설계 판단 |
| [`2026-09-06-getting-org-documents-into-rag.md`](2026-09-06-getting-org-documents-into-rag.md) | 조직 문서를 RAG 에 붙이는 층 — 파싱·변경 동기화·ACL·큐레이션·소유권. **운영 실패가 코어가 아니라 여기서 난다**는 가설의 검증 |
| [`2026-09-06-rag-communities.md`](2026-09-06-rag-communities.md) | RAG 실무자가 어디서 무엇을 이야기하나 — 커뮤니티 8곳·워크숍 3곳, 그리고 khala 가 무엇을 들고 갈 수 있고 무엇을 말하면 안 되는가 |
| [`2026-09-23-bug-diagnosis-agents-field-data.md`](2026-09-23-bug-diagnosis-agents-field-data.md) | 버그 제보·장애를 진단하는 AI 에이전트를 현업이 어떤 용도로 어느 수준까지 쓰는가 — 대기업 사내·상용 제품·독립 벤치마크·국내 사례·비용과 실패. 구현 착수 전 견적의 근거 |
| [`2026-09-25-canonical-link-feature-map-prior-art.md`](2026-09-25-canonical-link-feature-map-prior-art.md) | 「기능 지도에 세부마다 정본을 링크한다(임베딩 위에)」는 방식을 주창·시도한 선행 사례 — 데이터 거버넌스·요구사항 추적성·카탈로그와 검증 제품·RAG 권위 연구·조직 정책·국내. 통째로 한 곳은 없고 조각마다 이름이 있다. 예고된 실패는 링크 부패가 아니라 결정 부패 |
| [`2026-09-25-central-axis-information-model-prior-art.md`](2026-09-25-central-axis-information-model-prior-art.md) | 흩어진 문서·코드가 매달릴 「중심 축 정보 모델」을 세운 곳 — canonical/reference model·DDD·MDA/MBSE/ASoT·온톨로지·계약/명세·기대 상태와 조정. 완전한 축은 축 자체가 드리프트했고 살아남은 축의 조건 다섯 중 넷은 거버넌스. 설계 단위는 「판정과 그 생애주기」 |

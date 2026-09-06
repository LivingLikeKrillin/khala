# RAG 실무자는 어디서 무엇을 이야기하나 — 그리고 khala 는 거기 낄 수 있나

*조사 2026-09-06. 공개 자료만. 커뮤니티 8곳 · 학술 워크숍 3곳.*

---

## 0. 이 조사가 못 하는 것 (먼저)

**① 안에 안 들어가 봤다.** Discord·Slack 은 가입해야 보인다. 여기 적은 규모와 성격은
**밖에서 보이는 것**(공식 문서·통계 페이지·3자 요약)이고, 실제로 무슨 말이 오가는지는
r/Rag 를 뺀 나머지에서 **직접 확인하지 않았다.** 특히 "답의 질이 높다" 같은 평판 진술은
3자 블로그의 인상이지 측정이 아니다.

**② 수치가 뒤섞여 있다.** r/Rag 의 77,000명은 [GummySearch](https://gummysearch.com/r/Rag/)
라는 3자 분석 도구의 값이고, LangChain 의 "월 활성 50k+" 는 [벤더 자기 보고]를 모은
[통계 사이트](https://gitnux.org/langchain-statistics/)의 값이다. **서로 비교하지 마라** —
세는 단위가 다르다(구독자 vs 월 활성).

**③ 한 수치는 2차 인용이라 검증하지 않았다.** *"엔터프라이즈 RAG 배포의 73%가 다중홉
과제에서 비공식 정확도 감사를 통과하지 못한다"* 는
[ragaboutit](https://ragaboutit.com/7-rag-developer-challenges-reddit-reveals-in-2026/)이
NIST 분석을 인용한 것이고, **원문을 확인하지 않았다.** 인용하려면 원문부터 찾아라.
⛔ 이 문서를 근거로 그 수를 옮겨 적지 마라.

**④ 시점.** 2026-09-06 기준이다. 커뮤니티 규모와 활성은 빠르게 변한다.

---

## 1. 지도

| 곳 | 규모 (출처) | 성격 |
|---|---|---|
| [**r/Rag**](https://gummysearch.com/r/Rag/) | **77,000** · 연 +35k(+81%) [3자 분석] | 실무자. 게시물 유형이 **토론 145 · 프로젝트 공개 37 · 튜토리얼 10** 으로 잡힌다 |
| [**Ragas Discord**](https://docs.ragas.io/en/stable/community/) | 1,300+ · 코드 기여자 80+ [벤더] | **평가 전용.** 창립팀 오피스아워 |
| [LangChain Discord](https://gitnux.org/langchain-statistics/) | 월 활성 50k+ [벤더 집계] | 최대 규모. 프레임워크 중심 |
| LlamaIndex Discord | 미상 | 규모는 작고 **RAG 특정 문제에 답의 질이 높다**는 평 [3자 인상] |
| [Arize Phoenix](https://phoenix.arize.com/integration/ragas/) Slack | 미상 | 관측·트레이싱 |
| [**PyTorchKR**](https://discuss.pytorch.kr/) | 2018년 개설 | 한국어. RAG 서베이 번역·한국어 임베딩 질문이 실제로 오간다 |
| [vLLM.KR](https://kr.rebellions.ai/2026-vllm-korea-meetup/) | 밋업 80~90명 | 2026-04 밋업에 **"접근 통제 구조를 둔 RAG 에이전트"** 발표 |
| [PyTorch Day Korea 2026](https://pytorch.kr/) | 2026-10-31, AWS Korea | 발표 자리 |

**학술.** [ACL 2026 RAG 워크숍](https://www.aclweb.org/portal/content/1st-workshop-retrieval-augmented-generation-report-generation-acl-2026)
(장문 RAG + 엄격한 출처 표기 요구, shared task 포함) ·
[AAAI 2026 IR 워크숍](https://www.aclweb.org/portal/content/call-papers-workshop-new-frontiers-information-retrieval-aaai-2026) ·
[RAGE-KG 2026](https://2026.rage-kg.org/) (지식그래프 결합. **work-in-progress 를 명시적으로 받는다**).

---

## 2. 무엇을 이야기하나

실무 논의의 축은 일곱으로 정리된다 — **청킹 · 임베딩 선택 · 환각 탐지 · 다중 에이전트 ·
비용 귀속 · 보안 · 평가**.

반복되는 프레임은 **"데모는 되는데 프로덕션은 안 된다"** 하나다. r/Rag 에서 반응이 큰 글의
모양도 그쪽이다:

- *"No, RAG is not dead. Please stop asking."*
- **"15 Months Building a RAG System in Retirement: Lessons Learned"**
- *"Graph RAG Explained: What It Is, How It Works, and When You Actually Need It"*

⭐ **세 번째 제목의 `When You Actually Need It` 이 이 커뮤니티의 취향을 압축한다** — 기법
소개가 아니라 **언제 그것이 필요 없는지**를 말하는 글이 읽힌다.

평가 쪽은 도구가 여럿이고 역할이 갈린다: Ragas·DeepEval 은 오프라인, Arize Phoenix 는
**프로덕션 트레이싱**, TruLens 는 피드백 함수. [3자 비교](https://www.confident-ai.com/knowledge-base/compare/best-rag-evaluation-tools)

---

## 3. khala 는 낄 수 있나

### 3.1 있는 것 — 이 커뮤니티들이 구조적으로 못 만드는 종류

**① 측정된 실패.** 기법 추가 7전 7패, 철회한 측정, 사전 등록 규율. 공개 글이 실패를 안 적는
이유는 [`2026-09-04-org-knowledge-systems.md`](2026-09-04-org-knowledge-systems.md) §0 이 적은
그 편향과 같다 — **실패는 글이 되지 않는다.** 그래서 희소하다.

**② 한국어 정량치.** `nomic-embed-text`(영어 중심) vs `KURE-v1` 을 같은 코퍼스에서 대 봤다:

| | vector Recall@10 | fused ANN |
|---|---|---|
| nomic-embed-text | **≥0.402** | 0.777 |
| KURE-v1 | **≥0.975** | 0.988 |

p≈2e-7. 그리고 **첫 측정은 테스트가 벡터를 덮어써서 철회**했다는 기록이 함께 있다
(`nexus/docs/KOREAN_SEARCH_QUALITY.md` §3.4~3.5). ⚠ 이것도 **우리 자기 보고**다 — 라벨과
코퍼스가 우리 것이고 독립 검증이 없다. 밖에 내놓을 때 그 한계를 같이 적어야 한다.

**③ 거버넌스 각도.** supersession · 승인 게이트 · 문서 부채. 관행 사례 아홉이 전부 위층을
만들지만([`org-knowledge-systems`](2026-09-04-org-knowledge-systems.md)) 이 각도로 쓴 글은 드물다.

### 3.2 없는 것 — 이것이 참여 방식을 결정한다

- **채택자 0.** ⛔ *"우리 팀에서 쓴다"* 는 사실이 아니다. 그렇게 말하면 안 된다.
- **프레임워크가 아니다.** LangChain 자리를 다투는 물건이 아니라 한 사람이 만든 시스템이다.
  *"쓰세요"* 는 성립하지 않는다.
- **온보딩이 무겁다.** 컨테이너 여섯 개. 남이 5분 안에 못 돌린다.
- r/Rag 는 **자기 홍보를 별도 유형으로 분류한다.** 프로젝트 링크부터 던지면 그 칸에 들어간다.

⇒ **"만들었다" 가 아니라 "측정해 봤더니 이렇더라" 로 들어가야 한다.** 리포 포지셔닝이
이미 그렇게 적혀 있다 — 파는 것은 *만들었다* 가 아니라 **만들고 반증했다**.

### 3.3 가장 구체적인 자리 하나

PyTorchKR 의 [**"한국어 임베딩 모델"**](https://discuss.pytorch.kr/t/topic/8180) 스레드
(2025-11-12) — *RAG 용으로 지금 가장 성능 좋은 한국어 임베딩이 무엇인가*.

달린 답은 **LLM 이 생성한 것 둘**(KoELECTRA·KoBERT·KoGPT 추천 — 검색용 임베딩 모델이
아니다)과 지나가는 한 줄뿐이다. **아무도 측정치로 답하지 않았다.**

§3.1 ②가 그 질문의 답이고, 수와 p 값과 **철회 기록**까지 붙어 있다. 홍보가 아니라 답변이다.

⚠ 다만 스레드는 2025-11 자이고 참여가 적다. **답을 달아도 읽히지 않을 수 있다** — 그건
이 조사로 알 수 없다.

---

## 4. 처분

⛔ **이 문서는 무엇을 하라고 정하지 않는다.** 조사이지 결정이 아니다. 고를 수 있는 자리는
셋이고, 셋 다 비용과 성격이 다르다.

| | 크기 | 무엇이 필요한가 |
|---|---|---|
| PyTorchKR 스레드 답변 | 가장 작다 | 이미 있는 수. 링크 없이도 성립한다 |
| r/Rag 실패 기록 글 | 중간 | 7전 7패를 남이 읽을 형태로 쓰는 일. **자기 홍보로 읽히지 않게** 쓰는 것이 핵심 |
| PyTorch Day Korea 2026 (10/31) | 크다 | 발표 준비. 기한이 남아 있다 |

**어느 것을 하든 지켜야 할 것 둘** — 채택자가 없다는 사실을 숨기지 않는다 · 우리 수는
우리 라벨·우리 코퍼스에서 나온 자기 보고라고 밝힌다. 이 디렉터리의 규칙 3 을 남에게
적용하기 전에 우리에게 먼저 적용하는 것이다.

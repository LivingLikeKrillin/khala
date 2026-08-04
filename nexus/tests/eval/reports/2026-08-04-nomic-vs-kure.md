# 한국어 검색 평가 실행 보고

- **커버리지 (판정보다 먼저 읽는다)**: nomic-embed-text: 1896/1906 (99.5%) · KURE-v1: 1906/1906 (100.0%)
- **실행 시각**: 2026-08-04 03:20 UTC
- **팩**: ko-k8s-2026-08-01
- **라벨 리비전**: 2
- **질의**: 답변가능 40
- **벡터 다리**: 정확 스캔 (ko_eval_embeddings, ivfflat 아님 — SPEC §4.2)
- **융합**: 프로덕션 `_rrf_fusion` 그대로 (k=60)
- **nomic 팔**: {'model': 'nomic-embed-text', 'backend': 'ollama (창은 모델 빌드가 고정)', 'device': 'cpu', 'observed_dim': 768, 'refused': 10, 'prefixes': {'document': 'search_document: ', 'query': 'search_query: '}}
- **KURE 팔**: {'model': 'KURE-v1', 'backend': 'sentence-transformers (nlpai-lab/KURE-v1)', 'revision': 'd14c8a9423946e268a0c9952fecf3a7aabd73bd9', 'library': 'sentence-transformers 3.4.1, torch 2.13.0', 'device': 'cpu', 'normalized': True, 'max_seq_length': 8192, 'observed_dim': 1024, 'max_input_tokens': 3426, 'prefixes': {'document': '(없음)', 'query': '(없음)'}}
- **풀 구성원**: keyword/mecab · keyword/nori · vector×2 · fused×2 (모든 다리 top-10)
- **확증 분석**: 비교가능 부분집합 36/40질의 (벡터 다리)
- **수치의 성격**: **전부 하한(lower bound)** — 풀 판정 보류, 미판정 문서는 비관련으로 세어진다
- **기술 분석**: 전체 답변가능 질의 (벡터·융합)

> Pack A 는 khala 자신의 코퍼스가 아니라 같은 종류의 공개 대역 코퍼스다.
> 이 실행만으로 ADR-0008 §5(b) 가 닫히지 않는다.

## 다리별 (답변가능 질의 기준)

| 다리 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| vector/nomic | 40 | 0.402 | 0.352 | 20 |
| vector/KURE-v1 | 40 | 0.975 | 0.927 | 0 |
| fused/nomic | 40 | 0.777 | 0.536 | 5 |
| fused/KURE-v1 | 40 | 0.988 | 0.941 | 0 |

### 층별 — vector/nomic (서술용, 아무것도 결정하지 않는다)

| 층 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| compound | 8 | 0.375 | 0.317 | 4 |
| loanword | 8 | 0.250 | 0.250 | 6 |
| mixed | 8 | 0.938 | 0.747 | 0 |
| particle | 8 | 0.219 | 0.219 | 5 |
| spacing | 8 | 0.229 | 0.229 | 5 |

### 층별 — vector/KURE-v1 (서술용, 아무것도 결정하지 않는다)

| 층 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| compound | 8 | 1.000 | 0.938 | 0 |
| loanword | 8 | 1.000 | 0.906 | 0 |
| mixed | 8 | 0.938 | 0.938 | 0 |
| particle | 8 | 0.938 | 0.917 | 0 |
| spacing | 8 | 1.000 | 0.938 | 0 |

### 층별 — fused/nomic (서술용, 아무것도 결정하지 않는다)

| 층 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| compound | 8 | 0.750 | 0.588 | 1 |
| loanword | 8 | 0.396 | 0.333 | 4 |
| mixed | 8 | 1.000 | 0.887 | 0 |
| particle | 8 | 0.781 | 0.350 | 0 |
| spacing | 8 | 0.958 | 0.521 | 0 |

### 층별 — fused/KURE-v1 (서술용, 아무것도 결정하지 않는다)

| 층 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| compound | 8 | 1.000 | 1.000 | 0 |
| loanword | 8 | 1.000 | 0.768 | 0 |
| mixed | 8 | 1.000 | 1.000 | 0 |
| particle | 8 | 0.938 | 0.938 | 0 |
| spacing | 8 | 1.000 | 1.000 | 0 |

## 판정

- 승 27 · 패 1 · 무 8 (불일치쌍 28)
- **KURE-v1 우세 (p=0.000)**

## 기술 분석 (α 를 쓰지 않는다)

- 전체 질의·벡터: KURE-v1 우세 (p=0.000)
- 전체 질의·융합: KURE-v1 우세 (p=0.000)

> 위 '판정' 은 **비교가능 부분집합**의 확증 결과다(벡터 다리). 전체 질의 분석은
> 커버리지 격차를 포함한 사용자 관점의 기술이며, 모델 품질 주장으로 인용해서는 안 된다.
> 벡터 다리는 정확 스캔이라 프로덕션(ivfflat)보다 후하게 나온다 — 절대값이 아니라 두
> 모델의 차이를 읽는 자다. 그리고 Pack A 는 khala 자신의 코퍼스가 아니다 (SPEC §4.7).
> **모든 수치는 하한이다** — 풀 판정을 보류했으므로 미판정 문서가 비관련으로 세어진다.
> 그 페널티는 새 문서를 더 많이 건져 올린 팔이 더 많이 받는다: 결론 방향에 보수적이다.
> 이 실행의 결과는 **교체를 허가하지 않는다** — 정확 스캔이라 프로덕션(ivfflat)을 예측하지
> 못하고, 차원 변경(768→1024)이 ANN 거동을 또 바꾼다. 교체 SPEC 이 자기 측정을 져야 한다.


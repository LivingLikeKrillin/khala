# 한국어 검색 평가 실행 보고

- **실행 시각**: 2026-08-03 10:42 UTC
- **팩**: ko-k8s-2026-08-01
- **라벨 리비전**: 2
- **질의**: 답변가능 40 · 답변불가 5(집계 제외)
- **엔진**: Postgres to_tsquery + ts_rank_cd (양 팔 동일)
- **nori 분석기**: opensearch 2.17.1 + analysis-nori, decompound_mode=mixed, user_dictionary=none
- **mecab 정책**: mecab-ko POS allow-list ['NNG', 'NNP', 'SL', 'SN', 'VA', 'VV', 'XR']
- **nori 정책**: nori(decompound_mode=mixed, user_dictionary=none) + POS allow-list ['NNG', 'NNP', 'SL', 'SN', 'VA', 'VV', 'XR'] (mecab 팔과 동일)
- **allow-list 밖 nori 태그**: {'J': 68456, 'E': 63288, 'XSV': 41847, 'NNB': 7972, 'VCP': 7033, 'XSA': 6863, 'VX': 6732, 'MM': 6259}
- **풀 구성원**: mecab-ko, nori (둘 다 top-10)
- **미판정 후보**: 판정 완료

> Pack A 는 khala 자신의 코퍼스가 아니라 같은 종류의 공개 대역 코퍼스다.
> 이 실행만으로 ADR-0008 §5(b) 가 닫히지 않는다.

## 다리별 (답변가능 질의 기준)

| 다리 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| keyword/mecab-ko | 40 | 0.783 | 0.565 | 4 |
| keyword/nori-mixed | 40 | 0.850 | 0.578 | 3 |

### 층별 — keyword/mecab-ko (서술용, 아무것도 결정하지 않는다)

| 층 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| compound | 8 | 0.750 | 0.625 | 0 |
| loanword | 8 | 0.688 | 0.277 | 2 |
| mixed | 8 | 0.625 | 0.588 | 2 |
| particle | 8 | 0.938 | 0.463 | 0 |
| spacing | 8 | 0.917 | 0.875 | 0 |

### 층별 — keyword/nori-mixed (서술용, 아무것도 결정하지 않는다)

| 층 | n | Recall@10 | MRR@10 | 미스 |
|---|---:|---:|---:|---:|
| compound | 8 | 0.812 | 0.625 | 0 |
| loanword | 8 | 0.688 | 0.343 | 2 |
| mixed | 8 | 0.750 | 0.600 | 1 |
| particle | 8 | 1.000 | 0.531 | 0 |
| spacing | 8 | 1.000 | 0.792 | 0 |

## 판정

- 승 7 · 패 2 · 무 31 (불일치쌍 9)
- **이 표본 크기에서 측정 가능한 차이 없음 (p=0.180) — 현직(mecab-ko) 유지**

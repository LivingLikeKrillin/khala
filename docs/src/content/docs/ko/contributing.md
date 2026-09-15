---
title: 기여 가이드 (Contributing)
description: Khala 오픈소스 생태계 기여 절차 및 컨벤션 안내.
---

본 프로젝트와 관련 도구군은 오픈소스 엔지니어링 표준에 따라 공개적으로 개발 및 유지보수됩니다. 기여 작업은 [Khala 모노레포](https://github.com/LivingLikeKrillin/khala)의 서브프로젝트 디렉터리(`nexus/`, `observer/`, `arbiter/`, `probe/`, `adept/`)를 기반으로 수행되며, GitHub 이슈 트래커 및 풀 리퀘스트(PR)를 통해 진행됩니다.

생태계 공통 규약(아키텍처 불변식, 컴포넌트 네이밍, 도구별 독립 시맨틱 버저닝, Conventional Commits 규칙)은 [`CONVENTIONS.md`](https://github.com/LivingLikeKrillin/khala/blob/master/CONVENTIONS.md) 및 표준 용어집 [`docs/glossary.md`](https://github.com/LivingLikeKrillin/khala/blob/master/docs/glossary.md)에 정의되어 있습니다.

풀 리퀘스트 제출 전 로컬 환경에서 테스트 스위트 및 거버넌스 게이트(`check_readme_counts.py`, `check_terms.py`, `check_svg_fit.py`, `ledger_integrity.py` 등)의 통과를 확인해야 합니다.

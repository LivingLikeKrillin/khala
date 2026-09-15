---
title: Adept
description: 엔지니어링 인지 부채 정량 계측기. 도메인 산출물에 대한 검증된 이해도(Vouch)를 정량 평가하여 지식 결손을 측정함.
---

Adept는 조직의 인지 부채(Cognitive Debt)를 정량적으로 계측하고 관리하는 감사 프레임워크입니다. 시스템 사양과 코드가 고도화되는 환경에서, 단순 문서 열람 여부가 아닌 산출물의 실제 기술 명세를 바탕으로 구성된 평가 문항 통과 여부를 통해 **공학적 이해도(Vouch)**를 측정합니다.

Adept는 지식 기판을 기준 원장(Ledger)으로 운용합니다:
- **분모(필수 인지 지식)**: `adept.manifest.yaml`에 등록된 핵심 아티팩트 집합
- **분자(검증된 이해도)**: 유효한 보증(Vouch) 상태를 유지하는 아티팩트 집합
- **인지 부채(Cognitive Debt)**: 분모와 분자의 차이(\(1 - \text{Coverage}\)), 즉 현재 유효한 보증자가 부재한 미보증 아티팩트의 결손량

<svg class="kh-fig" viewBox="0 0 560 230" role="img" aria-label="Adept 인지 부채 계측 다이어그램: 등록된 12개 핵심 아티팩트 중 9개는 유효 보증 상태이며 3개는 보증 만료 또는 부재 상태임. 커버리지는 9/12(75%)이며, 미보증 아티팩트(retry-policy.md 등)가 우선 상각 대상 핫리스트로 분류됨.">
<defs><marker id="ad-ko-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="250" height="180" rx="8"/>
<text class="kh-fig-h" x="42" y="52">CRITICAL ARTIFACTS · 12</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="256" y2="64"/>
<rect class="kh-fig-track" x="44" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="44" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="158" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="44" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="120" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="158" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="42" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="60" y="187">보증됨 ×9</text>
<rect class="kh-fig-box-acc" x="150" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="168" y="187">만료/미보증 ×3</text>
<path class="kh-fig-line-acc" d="M274 118 L300 118" marker-end="url(#ad-ko-a)"/>
<rect class="kh-fig-panel" x="300" y="28" width="236" height="180" rx="8"/>
<text class="kh-fig-h" x="318" y="52">COVERAGE</text>
<line class="kh-fig-rule" x1="318" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="318" y="94">9 / 12</text>
<text class="kh-fig-d" x="318" y="122">retry-policy.md</text>
<text class="kh-fig-s" x="318" y="144">유효 보증자 부재</text>
<text class="kh-fig-d" x="318" y="176">→ 우선 보증 대상</text>
</svg>

## 핵심 기능 명세

- **보증(Vouch) 수명주기 및 불변성** — 검증된 이해 평가는 대상 아티팩트의 `content_hash`에 바인딩됩니다. 아티팩트 내용이 변경되면 기존 보증은 즉시 **만료(Stale)** 상태로 전이되어 이전 사양에 대한 이해가 자동으로 이월되지 않습니다.
- **간격 반복 평가 (Spaced Repetition)** — 문항별 숙련도와 시간 경과에 따라 재평가 주기를 산출하며, 주기 도래 시 재검증을 요구합니다.
- **보증 커버리지 및 미보증 핫리스트 (Orphan Hotlist)** — 조직 전체의 핵심 아티팩트 대비 유효 보증 비율을 산출하고, 보증자가 전무한 아티팩트를 핫리스트로 우선 분류하여 지식 결손을 사전 방지합니다.
- **저자 중립성 (Author Agnostic)** — 작성 주체(인간 엔지니어 또는 자율 코딩 에이전트)와 무관하게, 현재 시점에서 해당 사양을 책임지고 설명할 수 있는 담당자의 존재 여부만을 평가합니다.

## 실행 및 CLI 인터페이스

```bash
uv tool install ./adept    # 전역 CLI 도구 설치 (또는 pipx install ./adept)
```

`adept.manifest.yaml`이 위치한 프로젝트 루트 또는 하위 경로에서 실행합니다:

```bash
adept register PATH                    # 핵심 아티팩트 등록 (artifact_id 발급)
adept due --as PERSON                  # 평가 주기 도래 문항 및 평가 필요 아티팩트 조회
adept coverage --as PERSON             # 조직 보증 커버리지, 미보증 핫리스트, 취약 영역 출력
adept review ARTIFACT_ID --as PERSON   # 헤드리스 평가 세션 실행 (ANTHROPIC_API_KEY 필요)
```

팀 단위 협업 및 대시보드 인터페이스는 웹 기반 UI와 공유 저장소 백엔드를 제공하는 [`adept-web`](https://github.com/LivingLikeKrillin/khala/tree/master/adept-web)을 통해 지원됩니다.

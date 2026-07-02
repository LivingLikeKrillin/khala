---
title: Adept
description: 인지부채 측정기. 이름 있는 사람이 산출물을 여전히 보증할 수 있는지, 실제 내용에 근거한 채점형 이해 검사로 측정한다.
---

Adept는 인지부채에 대한 Khala의 답에서 원장(ledger)을 맡는 절반이다. 생태계의 나머지는 조직의 지식을 통제된 상태 — 승인되고, 최신이고, 인용되는 — 로 유지한다. Adept는 그 같은 기판을 반대편에서 읽으며 불편한 질문을 던진다: **이름 있는 사람이 아직 이것을 설명할 수 있는가?** "이해했습니다" 클릭 같은 고무도장이 아니라, 산출물의 실제 내용에서 생성된 채점형 이해 질문을 통과하는 것으로.

프레임은 원장이다. 등록된 핵심 산출물이 **분모** — 알아야 할 것. 유효한 보증(vouch)이 **분자** — 누군가 여전히 설명할 수 있는 것. 그 간극이 인지부채이고, 측정되기 때문에 장애 때 발견되는 대신 계획적으로 갚을 수 있다.

<svg class="kh-fig" viewBox="0 0 560 230" role="img" aria-label="Adept는 창고를 분모로 읽는다: 등록된 핵심 산출물 12개 중 9개는 유효한 보증이 있고 3개는 없다. 커버리지는 12분의 9; 보증자가 없는 산출물이 상환 핫리스트의 맨 위에 온다.">
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
<text class="kh-fig-s" x="168" y="187">낡음/없음 ×3</text>
<path class="kh-fig-line-acc" d="M274 118 L300 118" marker-end="url(#ad-ko-a)"/>
<rect class="kh-fig-panel" x="300" y="28" width="236" height="180" rx="8"/>
<text class="kh-fig-h" x="318" y="52">COVERAGE</text>
<line class="kh-fig-rule" x1="318" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="318" y="94">9 / 12</text>
<text class="kh-fig-d" x="318" y="122">retry-policy.md</text>
<text class="kh-fig-s" x="318" y="144">유효한 보증자 없음</text>
<text class="kh-fig-d" x="318" y="176">→ 먼저 갚는다</text>
</svg>

## 핵심 개념

- **보증(vouch).** 이름 있는 사람이 통과한 채점형 이해 검사이며, 산출물의 `content_hash`에 결박된다. 산출물이 바뀌면 보증은 자동으로 **낡는다(stale)** — 옛 버전에 대한 이해가 소리 없이 이월되지 않는다.
- **간격 반복.** 질문별 숙련도는 반복 사다리 위에 놓이고, 다시 통과할 때까지 재검사 대상으로 되돌아온다. 보증은 한 번 따는 배지가 아니라 유지하는 상태다.
- **커버리지.** 조직 수준 지표: 등록된 핵심 산출물 중 유효한 보증이 있는 비율. 그 여집합이 **고아 핫리스트** — 지금 아무도 보증할 수 없는 산출물이다. 그것부터 갚는다.
- **AI 저자 안전.** Adept는 git 히스토리를 조회하지 않는다. 산출물을 사람이 썼는지 에이전트가 썼는지는 무관하다. 유일한 질문은 *지금* 사람이 이해하고 있는가다.

## 빠른 시작

```bash
uv tool install ./adept    # 또는: pipx install ./adept — 전역 `adept` 명령 설치
```

프로젝트 어디서든 `adept`를 실행하면 된다 — 루트는 (현재 디렉터리에서 위로 올라가며 찾은) 가장 가까운 `adept.manifest.yaml`이다. 산출물 경로는 그 루트에 상대적으로 저장되므로 매니페스트는 클론 간에 이식 가능하다.

```bash
adept register PATH                    # 핵심 산출물 등록; artifact_id 출력
adept due --as PERSON                  # 재검사할 질문 / 질문이 필요한 산출물
adept coverage --as PERSON             # 커버리지, 고아 핫리스트, 약점 지도
adept review ARTIFACT_ID --as PERSON   # 헤드리스 자체 구동 (ANTHROPIC_API_KEY 필요)
```

에이전트 구동 루프(`due` → `save-questions` → `record-attempt` → `coverage`)에는 API 키가 필요 없다 — Claude Code 세션이 인지(질문 생성·채점·보완)를 공급한다. 모델을 직접 호출하는 것은 `adept review`뿐이다.

브라우저 + 서버 기반 팀 표면은 [`adept-web`](https://github.com/LivingLikeKrillin/khala/tree/master/adept-web)에 있다 — 같은 측정기에 공유 백엔드(파일 또는 Postgres)를 붙인 것이다.

:::note[마지막 검증]
`adept/README.md`에서 옮겨 적음. 사이트 기준 재실행 검증은 대기 중.
:::

---
title: Observer
description: 플랫폼 인식 PR 분석기이자 API 계약 검증기. 리뷰를 응집도·하위호환성·조직 규정에 근거시킨다.
---

Observer는 리뷰어가 머릿속에 들고 있어야 할 맥락에 변경을 근거시키는 도구입니다. **플랫폼 인식 PR 분석기 + API 계약 검증기**로, 반복되는 세 가지 리뷰 질문을 결정론적 검사로 바꿉니다:

1. **이 PR 범위가 적절한가?** 같은 7개 파일이 Spring Boot에서는 하나의 응집된 변경이고 Next.js에서는 분리해야 할 세 관심사일 수 있습니다. 파일 수로 판단하면 오판하므로, Observer는 플랫폼 프로파일 대비 *논리적 응집도*로 판단합니다.
2. **API 변경이 하위 호환인가?** nullable 누락, 에러 응답 불일치, breaking change가 리뷰에서 빠집니다. Observer는 스펙을 린트하고 base와 diff합니다.
3. **이 변경이 규정에 맞는가?** 가이드라인이 있어도 리뷰어가 매번 기억해 대조하기 어렵습니다. Observer는 PR 타입을 추론해 맞는 체크리스트를 생성하고, Nexus가 연결돼 있으면 관련 규정과 영향까지 붙입니다.

관통하는 원칙 하나: **정상일 때는 아무 말도 하지 않는다.** 노이즈는 신뢰를 죽입니다. 경고할 때는 어떻게 분할할지까지 제안합니다.

한마디로: 범위·계약·규정 준수를 근거시켜 PR 리뷰를 정직하게 유지합니다. Nexus가 연결되면 더 풍부해지지만, 없어도 완전히 동작합니다.

<svg class="kh-fig" viewBox="0 0 560 220" role="img" aria-label="Observer는 3개 변경 파일에 역할을 배정한다 — api(routes/pay.py, schemas/pay.py)와 data(models/ledger.py) — 두 역할이 섞였음을 발견하고, 병합 순서를 보존한 채 PR-a(api)와 PR-b(data)로 분할을 제안한다.">
<defs><marker id="ob-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="284" height="168" rx="8"/>
<text class="kh-fig-h" x="42" y="52">SCOPE · 3 FILES</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="290" y2="64"/>
<text class="kh-fig-h" x="42" y="88">API</text>
<text class="kh-fig-d" x="88" y="88">routes/pay.py</text>
<text class="kh-fig-d" x="88" y="108">schemas/pay.py</text>
<text class="kh-fig-h" x="42" y="140">DATA</text>
<text class="kh-fig-d" x="88" y="140">models/ledger.py</text>
<text class="kh-fig-s" x="42" y="176">cohesion scored · roles matched</text>
<path class="kh-fig-line-acc" d="M308 112 L334 112" marker-end="url(#ob-a)"/>
<rect class="kh-fig-panel" x="334" y="28" width="202" height="168" rx="8"/>
<text class="kh-fig-h" x="352" y="52">VERDICT</text>
<line class="kh-fig-rule" x1="352" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="352" y="92">mixed · 2 roles</text>
<text class="kh-fig-d" x="352" y="122">propose split</text>
<text class="kh-fig-d" x="352" y="146">› PR-a  api</text>
<text class="kh-fig-d" x="352" y="166">› PR-b  data</text>
<text class="kh-fig-s" x="352" y="186">merge order preserved</text>
</svg>

## 핵심 개념

- **플랫폼 프로파일** — 프레임워크별(Spring Boot, Next.js, React SPA) 파일 패턴 → 역할 매핑. 역할이 모여 **응집 그룹**을 이룹니다.
- **범위 분석** — 변경 파일에 역할을 부여하고 응집 그룹에 매칭, severity를 매겨 관심사가 섞였으면 머지 순서까지 담은 분할을 제안합니다.
- **관심사 드리프트** — 편집 중 현재 변경과 *다른* 관심사의 파일이 들어오면 즉시 경고합니다.
- **API 린트 + diff** — 10개 내장 룰(`observer/nullable`, `observer/error-response` 등)로 스펙을 검사하고, base 대비 breaking change를 감지합니다.
- **PR 타입 → 체크리스트** — 10개 PR 타입이 각각 리뷰 체크리스트로 매핑됩니다.
- **Nexus는 선택적** — 없어도 모든 기능이 동작하고, 있으면 규정·영향·설계-관측 갭이 더해집니다.

설치(npm 미게시 — 저장소에서 `pnpm install && pnpm build`), 명령어(`observer check` 등), MCP 등록은 영어 페이지([Observer](/tools/observer/))를 참고하세요.

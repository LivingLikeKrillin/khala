# 검색답변 신뢰 신호 배지 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 리더가 검색 답변의 각 근거를 볼 때 그 문서의 거버넌스 신뢰 등급(거버넌스/추적/메모)을 배지로 즉시 calibrate하게 한다 — nexus 백엔드 무변경.

**Architecture:** 순수 프론트 표현 계층. 응답에 이미 실린 `doc_type`(#56)을 `trustSignal()` 순수 함수가 3개 신뢰 톤으로 번역하고, 채팅 근거 패널과 문서 목록 배지에 렌더한다. tier 그룹핑은 specledger `document_types.yaml`(정본)의 terse 표현 미러다. nexus 서버는 tier를 파생하지 않는다(S3 경계 보존).

**Tech Stack:** Vanilla ES modules (nexus/nexus/web/js), CSS (style.css). JS 테스트 러너 없음 → 순수 함수는 일회성 `node` 어설션으로, 렌더는 verify 스킬(런타임 관찰)로 검증.

**Spec:** `docs/superpowers/specs/2026-06-25-search-answer-trust-signal-design.md`

---

## File Structure

- **Create** `nexus/nexus/web/js/doctype-signal.js` — 순수 함수 `trustSignal(docType)`. 유일 책임: 축-A doc_type → `{label, tier, tone, note}` 매핑(+ 보수적 기본). DOM/네트워크 의존 0.
- **Modify** `nexus/nexus/web/js/views/chat.js` — `renderEvidence()`가 근거 항목에 신뢰 배지 렌더(import 1줄 + ev-head에 배지 1줄).
- **Modify** `nexus/nexus/web/js/views/documents.js` — `renderTable()`의 기존 `doc-type-badge`에 tone 클래스 + 툴팁 결합(import 1줄 + td 1줄).
- **Modify** `nexus/nexus/web/css/style.css` — `.trust-badge` + 3 tone 변형(`governed`/`tracked`/`memo`) 추가.

**계약 고정(불변):** `trustSignal` 반환 키는 정확히 `label`(string), `tier`(string), `tone`(`'governed'|'tracked'|'memo'`), `note`(string). CSS 클래스명은 `tone` 값과 **글자 그대로** 일치해야 한다(`.trust-badge--governed` 등) — 불일치 시 스타일 누락이 조용히 발생.

---

## Chunk 1: 신뢰 신호 배지

### Task 1: `trustSignal()` 순수 모듈

**Files:**
- Create: `nexus/nexus/web/js/doctype-signal.js`

- [ ] **Step 1: 모듈 작성**

```javascript
/**
 * doc_type(축-A 타입) → 리더용 신뢰 신호.
 *
 * ⚠️ 미러: 타입→tier 그룹핑의 정본은 specledger `document_types.yaml`(거버넌스 경계)이다.
 * 여기엔 검색 리더용 *짧은 신뢰 신호*만 둔다(풀 운용 가이드는 specledger `guide(type)`).
 * S3 결정(nexus는 tier 파생 안 함)을 지키려 이 매핑은 뷰 계층 표현물로만 존재한다.
 * — 기존 nexus a2a/external_ingest_skill.py `_KIND_ALIASES` 미러와 동일한 디커플링 패턴.
 */

const _GOVERNED = {
  tier: '거버넌스', tone: 'governed', label: '승인된 거버넌스 결정',
  note: '승인 게이트를 거친 정본 결정 — 상태(accepted/superseded) 확인',
};
const _TRACKED = {
  tier: '추적', tone: 'tracked', label: '추적 문서',
  note: '리뷰되나 승인 게이트 없음 — drift/staleness 주의',
};
const _MEMO = {
  tier: '메모', tone: 'memo', label: '비거버넌스 메모',
  note: '정본 아님 — 인덱싱·검색용 참고. 정본이면 promote 필요',
};

// 축-A 타입 → 신뢰 등급. 미등록/빈값은 보수적으로 메모(specledger default_tier=T3 정책과 일치).
const _BY_TYPE = {
  ADR: _GOVERNED, DESIGN: _GOVERNED, RFC: _GOVERNED,
  PRD: _TRACKED, RUNBOOK: _TRACKED, POSTMORTEM: _TRACKED,
  NOTE: _MEMO,
};

/**
 * @param {string} docType 축-A 타입(대소문자/공백 무시). 미지/빈값 → 메모.
 * @returns {{label:string, tier:string, tone:'governed'|'tracked'|'memo', note:string}}
 */
export function trustSignal(docType) {
  const key = String(docType || '').trim().toUpperCase();
  return _BY_TYPE[key] || _MEMO;
}
```

- [ ] **Step 2: 일회성 node 어설션(러너 없음 — 순수 함수 sanity)**

Run:
```bash
cd "nexus/nexus/web/js" && node --input-type=module -e "
import { trustSignal } from './doctype-signal.js';
const a = trustSignal('ADR'); if (a.tone !== 'governed') throw new Error('ADR governed 실패');
const r = trustSignal('runbook'); if (r.tone !== 'tracked') throw new Error('대소문자 무시 실패');
const n = trustSignal('NOTE'); if (n.tone !== 'memo') throw new Error('NOTE memo 실패');
const e = trustSignal(''); if (e.tone !== 'memo') throw new Error('빈값→memo 실패');
const g = trustSignal('!!garbage!!'); if (g.tone !== 'memo') throw new Error('미지값→memo 실패');
const u = trustSignal(undefined); if (u.tone !== 'memo') throw new Error('undefined→memo 실패');
console.log('OK: governed/tracked/memo + 대소문자/빈값/미지/undefined 보수적 기본 확인');
"
```
Expected: `OK: ...` 출력, exit 0. (실패 시 throw로 비-0.)

> 리뷰어 권고 반영: *빈값*뿐 아니라 `!!garbage!!`·`undefined` 같은 **미지값→memo** 분기를 명시 검증(런타임 NOTE 코퍼스 관찰로는 안 닿는 분기).

- [ ] **Step 3: 커밋**

```bash
git add nexus/nexus/web/js/doctype-signal.js
git commit -m "feat(web): trustSignal() — doc_type→신뢰등급 순수 매핑"
```

### Task 2: CSS tone 배지

**Files:**
- Modify: `nexus/nexus/web/css/style.css` (`.doc-type-badge` 근처, 약 734줄)

- [ ] **Step 1: `.trust-badge` + 3 tone 추가**

기존 배지 패턴(`.doc-type-badge`, `.status-badge`)과 브랜드 토큰을 따른다. style.css 끝 또는 `.doc-type-badge` 블록 근처에 추가:

실재 토큰(확인됨, style.css `:root`): `--ink-100`/`--ink-500`/`--hairline`/`--hairline-strong` 존재, **`--ink-60`은 없음**(→ `--ink-500` 사용). 기존 `.doc-table .doc-type-badge { color: var(--cyan-300) }`(specificity 0-2-0)가 문서뷰에서 tone 색을 덮으므로, 문서뷰용 **상위 specificity 규칙**을 함께 추가한다.

```css
/* 신뢰 신호 배지 — tone 값(governed/tracked/memo)과 클래스명이 정확히 일치해야 함 */
.trust-badge {
  display: inline-block;
  font-size: 11px;
  line-height: 1.4;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  color: var(--ink-100);
  white-space: nowrap;
  cursor: default;
}
.trust-badge--governed { border-color: #2f7d4f; color: #2f7d4f; }
.trust-badge--tracked  { border-color: #9a6a1f; color: #9a6a1f; }
.trust-badge--memo     { border-color: var(--hairline-strong); color: var(--ink-500); }

/* 문서뷰: 기존 `.doc-table .doc-type-badge`(0-2-0)를 이기도록 동일 스코프 + 클래스(0-3-0) */
.doc-table .doc-type-badge.trust-badge--governed { border-color: #2f7d4f; color: #2f7d4f; }
.doc-table .doc-type-badge.trust-badge--tracked  { border-color: #9a6a1f; color: #9a6a1f; }
.doc-table .doc-type-badge.trust-badge--memo     { border-color: var(--hairline-strong); color: var(--ink-500); }
```

> tone별 색은 의미(승인=녹/추적=호박/메모=중립)만 지키면 됨. 구현 시 style.css `:root`에서 실제 변수명을 한 번 더 대조(여기 명시한 `--ink-500`/`--hairline-strong`이 정본).

- [ ] **Step 2: 커밋**

```bash
git add nexus/nexus/web/css/style.css
git commit -m "style(web): trust-badge tone 3종(governed/tracked/memo)"
```

### Task 3: 채팅 근거 패널에 배지 (주 surface)

**Files:**
- Modify: `nexus/nexus/web/js/views/chat.js` (import 부 ~6줄, `renderEvidence` ~358줄)

- [ ] **Step 1: import 추가**

`chat.js` 상단 import 블록(6–8줄)에 추가:
```javascript
import { trustSignal } from '../doctype-signal.js';
```

- [ ] **Step 2: 근거 항목에 배지 렌더**

`renderEvidence`의 `snippets.map(...)` 안, `ev-head` 블록을 다음으로 교체(현재 `ev-index`+`ev-title` 두 span 뒤에 배지 추가):
```javascript
      <div class="ev-head">
        <span class="ev-index">${i + 1}</span>
        <span class="ev-title">${escapeHtml(s.doc_title || '(제목 없음)')}</span>
        ${(() => { const t = trustSignal(s.doc_type);
          return `<span class="trust-badge trust-badge--${t.tone}" title="${escapeHtml(t.note)}">${escapeHtml(t.label)}</span>`; })()}
      </div>
```
(escapeHtml은 chat.js의 로컬 함수 — 확인됨 chat.js:464.)

- [ ] **Step 3: 커밋**

```bash
git add nexus/nexus/web/js/views/chat.js
git commit -m "feat(web): 근거 패널에 신뢰 신호 배지(chat renderEvidence)"
```

### Task 4: 문서 목록 배지 강화

**Files:**
- Modify: `nexus/nexus/web/js/views/documents.js` (import ~5줄, `renderTable` ~78줄)

- [ ] **Step 1: import 추가**

```javascript
import { trustSignal } from '../doctype-signal.js';
```

- [ ] **Step 2: doc-type-badge 강화**

`renderTable`의 doc_type `<td>`(78줄)를 교체 — raw 타입 텍스트는 유지하되 tone 클래스 + 툴팁(note) 결합:
```javascript
      <td>${(() => { const t = trustSignal(d.doc_type);
        return `<span class="doc-type-badge trust-badge--${t.tone}" title="${escapeHtml(t.label + ' · ' + t.note)}">${escapeHtml(d.doc_type || '-')}</span>`; })()}</td>
```
(documents.js의 로컬 escapeHtml 사용 — 확인됨 documents.js:104. tone 색은 Task 2의 `.doc-table .doc-type-badge.trust-badge--*` 상위 specificity 규칙이 기존 `--cyan-300`을 이김.)

- [ ] **Step 3: 커밋**

```bash
git add nexus/nexus/web/js/views/documents.js
git commit -m "feat(web): 문서 목록 doc-type 배지에 신뢰 톤+툴팁"
```

### Task 5: 런타임 검증 (verify 스킬)

**Files:** 없음(관찰만).

- [ ] **Step 1: 앱 기동 확인 + 정적 자산 최신화**

스택이 떠 있으면 web은 마운트된 정적 파일이라 즉시 반영. 아니면 `cd nexus && docker compose up -d`.

- [ ] **Step 2: 채팅 근거 배지 관찰**

verify 스킬로 실제 적재된 코퍼스(NOTE 12건)에 채팅 검색 → 근거 패널 각 항목에 `비거버넌스 메모`(memo 톤) 배지 + 툴팁 렌더 확인. (브라우저 픽셀 구동 불가 시, `/search/answer` 응답의 `evidence_snippets[*].doc_type`이 채워짐 + 정적 `doctype-signal.js`가 서빙됨을 HTTP로 확인하고, 매핑은 Step Task1의 node 어설션으로 보강.)

- [ ] **Step 3: 문서 목록 배지 관찰**

문서 탭에서 doc-type 배지가 memo 톤 + 툴팁으로 렌더 확인.

- [ ] **Step 4: 최종 정리/PR**

verify 결과를 근거로 PR 생성 → CI 9그린 → master 머지.

---

## 검증 요약

- **순수 함수(`trustSignal`):** node 어설션(governed/tracked/memo, 대소문자, 빈값/미지/undefined→memo).
- **렌더(chat/documents):** verify 스킬 런타임 관찰 + 정적 자산/응답 HTTP 확인.
- **경계:** nexus 백엔드 변경 파일 0 — diff가 `web/` 와 spec/plan 문서로만 구성됨을 확인(S3 보존 증거).

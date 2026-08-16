/**
 * 채팅 뷰.
 * SSE 스트리밍 답변 + Evidence 패널 + 인라인 그래프.
 */

import { getStatus, streamAnswer, suggestEntities } from '../api.js';
import { corpusHint } from '../corpus-hint.js';
import { forRequest } from '../history.js';
import { failureNotice } from '../llm-failure.js';
import { citationReport } from '../citations.js';
import { trustSignal } from '../doctype-signal.js';
import { anchorSignal } from '../anchor-signal.js';
import { renderMarkdown } from '../components/markdown.js';
import { showToast } from '../components/toast.js';

let chatHistory = [];
let isStreaming = false;
let autocompleteTimer = null;
let autocompleteIndex = -1;
let autocompleteItems = [];

// 신규 사용자(자기 문서를 막 올린)에게도 맞는 corpus-무관 예시. 데모 전용 고유명사·운영자
// 개념(설계-관측 diff) 대신, 어떤 문서 묶음에도 통하는 일반 질문.
const SUGGESTIONS = [
  '방금 올린 문서 요약해줘',
  '이건 어떻게 동작해?',
  '핵심 결정과 그 근거는?',
];

export function render(container) {
  container.innerHTML = `
    <div class="chat-layout">
      <div class="chat-main">
        <div class="chat-history" id="chat-history">
          <div class="chat-empty" id="chat-empty">
            <div class="chat-empty-crystal" aria-hidden="true">
              <svg viewBox="0 0 64 64">
                <defs>
                  <linearGradient id="empty-crystal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#c7f1ff"/>
                    <stop offset="55%" stop-color="#4fb6ee"/>
                    <stop offset="100%" stop-color="#2272c4"/>
                  </linearGradient>
                </defs>
                <path d="M30 24 C24 18 23 12 27.5 7" fill="none" stroke="#8fdcff" stroke-width="2.2" stroke-linecap="round" opacity="0.8"/>
                <path d="M34 24 C40 18 41 12 36.5 7" fill="none" stroke="#8fdcff" stroke-width="2.2" stroke-linecap="round" opacity="0.8"/>
                <path d="M32 19 L41 36 L32 50 L23 36 Z" fill="url(#empty-crystal)"/>
                <path d="M32 19 L32 50 L23 36 Z" fill="#ffffff" opacity="0.16"/>
                <path d="M32 19 L41 36 L32 36 Z" fill="#ffffff" opacity="0.30"/>
              </svg>
            </div>
            <div class="chat-empty-title">무엇이든 물어보세요</div>
            <div class="chat-empty-hint">올린 문서에서 출처와 함께 답합니다 — 추측 없이, 근거만</div>
            <div class="chat-empty-hint">팁: <span class="at">@이름</span> 으로 특정 서비스·엔티티를 지정</div>
            <div class="chat-suggest" id="chat-suggest">
              ${SUGGESTIONS.map(s => `<button type="button" class="suggest-chip">${escapeHtml(s)}</button>`).join('')}
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <div class="chat-input-wrapper" style="position:relative">
            <div class="autocomplete-dropdown" id="autocomplete-dropdown"></div>
            <textarea id="chat-input" rows="1"
              placeholder="무엇이든 물어보세요 — @ 로 서비스·엔티티 지정"
            ></textarea>
            <button id="chat-send" type="button">전송</button>
          </div>
        </div>
      </div>
      <div class="evidence-panel hidden" id="evidence-panel">
        <div class="evidence-header">
          <span>근거</span>
          <span id="evidence-count"></span>
        </div>
        <div class="evidence-list" id="evidence-list"></div>
        <div class="evidence-provenance" id="evidence-provenance"></div>
      </div>
    </div>
  `;

  renderChatHistory();
  bindEvents();
  maybeShowEmptyCorpus();
}

/**
 * 코퍼스가 비었으면 예시 질문 대신 "먼저 문서를 올리세요" 를 보여준다.
 * 안 그러면 새 사용자가 예시를 눌러도 전부 "결과 없음" 으로 끝나 도구가 고장 난 듯 보인다.
 */
async function maybeShowEmptyCorpus() {
  let hint = null;
  try {
    const { data } = await getStatus();
    hint = corpusHint(data?.documents_count);
  } catch {
    return;                          // status 실패는 상태바가 알린다 — 여기선 조용히 둔다
  }
  if (!hint) return;                 // 문서가 있다 → 예시 질문 그대로

  const suggest = document.getElementById('chat-suggest');
  const title = document.querySelector('#chat-empty .chat-empty-title');
  const hints = document.querySelectorAll('#chat-empty .chat-empty-hint');
  if (suggest) suggest.style.display = 'none';   // 답 못 할 예시는 감춘다
  if (title) title.textContent = hint.title;
  if (hints[0]) hints[0].textContent = hint.body;
  if (hints[1]) hints[1].style.display = 'none';
}

function bindEvents() {
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');

  sendBtn.addEventListener('click', () => submitQuery());

  // 추천 질문 칩 → 입력 채우고 즉시 전송
  const suggest = document.getElementById('chat-suggest');
  if (suggest) {
    suggest.querySelectorAll('.suggest-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        input.value = chip.textContent;
        submitQuery();
      });
    });
  }

  input.addEventListener('keydown', (e) => {
    // Autocomplete 키보드 네비게이션
    const dropdown = document.getElementById('autocomplete-dropdown');
    if (dropdown.classList.contains('visible')) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        autocompleteIndex = Math.min(autocompleteIndex + 1, autocompleteItems.length - 1);
        highlightAutocomplete();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        autocompleteIndex = Math.max(autocompleteIndex - 1, 0);
        highlightAutocomplete();
        return;
      }
      if (e.key === 'Enter' && autocompleteIndex >= 0) {
        e.preventDefault();
        selectAutocomplete(autocompleteItems[autocompleteIndex]);
        return;
      }
      if (e.key === 'Escape') {
        hideAutocomplete();
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitQuery();
    }
  });

  // 자동완성: @ 트리거
  input.addEventListener('input', () => {
    autoResize(input);
    handleAutocomplete(input);
  });

  // 한국어 IME compositionend 대응
  input.addEventListener('compositionend', () => {
    handleAutocomplete(input);
  });
}

function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// ── Autocomplete ──

function handleAutocomplete(input) {
  clearTimeout(autocompleteTimer);
  const val = input.value;
  const cursor = input.selectionStart;
  const before = val.slice(0, cursor);
  const match = before.match(/@(\S*)$/);

  if (!match) {
    hideAutocomplete();
    return;
  }

  const q = match[1];
  if (q.length < 1) return;

  autocompleteTimer = setTimeout(async () => {
    try {
      const { data } = await suggestEntities(q);
      if (!data || data.length === 0) {
        hideAutocomplete();
        return;
      }
      autocompleteItems = data;
      autocompleteIndex = -1;
      showAutocomplete(data);
    } catch {
      hideAutocomplete();
    }
  }, 300);
}

function showAutocomplete(items) {
  const dropdown = document.getElementById('autocomplete-dropdown');
  // 엔티티 값은 인제스트된 문서에서 추출되므로 신뢰 불가 → 반드시 escape
  dropdown.innerHTML = items.map((item, i) => `
    <div class="autocomplete-item" data-index="${i}">
      <span class="ac-type">${escapeHtml(item.type || '')}</span>
      <span class="ac-name">${escapeHtml(item.name || '')}</span>
      <span class="ac-desc">${escapeHtml(item.description || '')}</span>
    </div>
  `).join('');
  dropdown.classList.add('visible');

  dropdown.querySelectorAll('.autocomplete-item').forEach(el => {
    el.addEventListener('click', () => {
      selectAutocomplete(items[parseInt(el.dataset.index)]);
    });
  });
}

function hideAutocomplete() {
  document.getElementById('autocomplete-dropdown').classList.remove('visible');
  autocompleteItems = [];
  autocompleteIndex = -1;
}

function highlightAutocomplete() {
  const items = document.querySelectorAll('.autocomplete-item');
  items.forEach((el, i) => {
    el.classList.toggle('selected', i === autocompleteIndex);
  });
}

function selectAutocomplete(item) {
  const input = document.getElementById('chat-input');
  const val = input.value;
  const cursor = input.selectionStart;
  const before = val.slice(0, cursor);
  const after = val.slice(cursor);
  const replaced = before.replace(/@\S*$/, `@${item.name} `);
  input.value = replaced + after;
  input.selectionStart = input.selectionEnd = replaced.length;
  hideAutocomplete();
  input.focus();
}

// ── 쿼리 제출 ──

async function submitQuery() {
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query || isStreaming) return;

  isStreaming = true;
  input.value = '';
  autoResize(input);
  document.getElementById('chat-send').disabled = true;

  // 빈 화면 숨기기
  const empty = document.getElementById('chat-empty');
  if (empty) empty.style.display = 'none';

  // 사용자 메시지
  chatHistory.push({ role: 'user', content: query });
  appendBubble('user', query);

  // 어시스턴트 버블 (스트리밍용)
  const bubbleId = `msg-${Date.now()}`;
  chatHistory.push({ role: 'assistant', content: '', id: bubbleId });
  appendBubble('assistant', '', bubbleId, true);

  let fullAnswer = '';

  try {
    await streamAnswer(query, {
      onEvidence(data) {
        renderEvidence(data.evidence_snippets || [], data.provenance || []);
        // route 표시
        const bubble = document.getElementById(bubbleId);
        if (bubble && data.route_used) {
          const tag = bubble.querySelector('.route-tag');
          if (tag) tag.textContent = data.route_used;
        }
      },
      onGraph(data) {
        renderInlineGraph(bubbleId, data);
      },
      onDelta(data) {
        fullAnswer += data.text;
        updateBubble(bubbleId, fullAnswer, true);
      },
      onDone(data) {
        // 생성 실패는 답변이 아니다. 서버가 분류한 사유(quota/auth/…)로 갈라 말한다 —
        // "잠시 후 다시" 는 기다리면 나아질 때만 참이다 (js/llm-failure.js).
        const notice = failureNotice(data);
        if (notice) showToast(notice, 'error');
        updateBubble(bubbleId, fullAnswer, false);
        renderCitations(bubbleId, citationReport(data.citations));
        // 히스토리 업데이트
        const entry = chatHistory.find(h => h.id === bubbleId);
        if (entry) entry.content = fullAnswer;
      },
      onError(data) {
        showToast(data.error || '스트리밍 에러', 'error');
        updateBubble(bubbleId, fullAnswer || '오류가 발생했습니다.', false);
      },
    }, {
      // 이번 질문과 아직 비어 있는 어시스턴트 버블은 **이미 chatHistory 에 들어가 있다**.
      // forRequest 가 그 둘을 떼고, 상한(턴 수·바이트)까지 맞춰 준다.
      history: forRequest(chatHistory),
    });
  } catch (err) {
    showToast(err.message, 'error');
    updateBubble(bubbleId, '서버와 연결할 수 없습니다.', false);
  }

  isStreaming = false;
  document.getElementById('chat-send').disabled = false;
  document.getElementById('chat-input').focus();
}

// ── 버블 렌더링 ──

function appendBubble(role, content, id = null, streaming = false, animate = true) {
  const history = document.getElementById('chat-history');
  const bubble = document.createElement('div');
  // 'rise'는 새로 추가되는 버블에만 — 히스토리 재생 시엔 생략해 매번 솟지 않게 한다.
  bubble.className = `chat-bubble ${role}${animate ? ' rise' : ''}`;
  if (id) bubble.id = id;

  if (role === 'user') {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = `
      <div class="route-tag"></div>
      <div class="bubble-content">${content ? renderMarkdown(content) : ''}</div>
      ${streaming ? '<span class="streaming-cursor"></span>' : ''}
    `;
  }

  history.appendChild(bubble);
  history.scrollTop = history.scrollHeight;
}

function updateBubble(id, content, streaming) {
  const bubble = document.getElementById(id);
  if (!bubble) return;

  const contentEl = bubble.querySelector('.bubble-content');
  if (contentEl) {
    contentEl.innerHTML = renderMarkdown(content);
  }

  const cursor = bubble.querySelector('.streaming-cursor');
  if (!streaming && cursor) cursor.remove();
  if (streaming && !cursor) {
    bubble.insertAdjacentHTML('beforeend', '<span class="streaming-cursor"></span>');
  }

  const history = document.getElementById('chat-history');
  history.scrollTop = history.scrollHeight;
}

function renderChatHistory() {
  if (chatHistory.length === 0) return;
  const empty = document.getElementById('chat-empty');
  if (empty) empty.style.display = 'none';

  for (const msg of chatHistory) {
    if (msg.role === 'user') {
      appendBubble('user', msg.content, null, false, false);
    } else {
      appendBubble('assistant', msg.content, msg.id, false, false);
    }
  }
}

// ── Evidence 패널 ──

function renderEvidence(snippets, provenance) {
  const panel = document.getElementById('evidence-panel');
  panel.classList.remove('hidden');

  document.getElementById('evidence-count').textContent = `${snippets.length}건`;

  // 상대 관련도: 집합 내 최고 점수 대비 비율로 막대를 채운다 (raw float 노출 대신).
  const maxScore = Math.max(...snippets.map(s => s.score || 0), 1e-9);

  const list = document.getElementById('evidence-list');
  list.innerHTML = snippets.map((s, i) => {
    const pct = Math.round(((s.score || 0) / maxScore) * 100);
    return `
    <div class="evidence-item" title="${escapeHtml(s.source_uri || '')}">
      <div class="ev-head">
        <span class="ev-index">${i + 1}</span>
        <span class="ev-title">${escapeHtml(s.doc_title || '(제목 없음)')}</span>
        ${(() => { const t = trustSignal(s.doc_type);
          return `<span class="trust-badge trust-badge--${t.tone}" title="${escapeHtml(t.note)}">${escapeHtml(t.label)}</span>`; })()}
        ${(() => { const a = anchorSignal(s.code_anchors);
          return a ? `<span class="anchor-badge anchor-badge--${a.tone}" title="${escapeHtml(a.note)}">${escapeHtml(a.label)}</span>` : ''; })()}
      </div>
      <div class="ev-path">${escapeHtml(s.section_path || '')}</div>
      <div class="ev-text">${escapeHtml(s.text || '')}</div>
      <div class="ev-relevance" title="관련도 ${pct}%">
        <div class="ev-bar"><div class="ev-bar-fill" style="width:${pct}%"></div></div>
        <span class="ev-pct">${pct}%</span>
      </div>
    </div>`;
  }).join('');

  const provEl = document.getElementById('evidence-provenance');
  if (provenance.length > 0) {
    provEl.innerHTML = `<h4>출처</h4>` + provenance.map(p => {
      const uri = p.source_uri || '';
      // 사람이 읽는 제목 우선, 원본 경로(source_uri)는 추적용으로 hover 에만.
      const label = escapeHtml(p.doc_title || p.source_uri || p.doc_rid || '');
      const tip = escapeHtml(p.source_uri || p.source_version || '');
      const isLink = /^https?:\/\//.test(uri);
      return isLink
        ? `<a href="${encodeURI(uri)}" target="_blank" rel="noopener noreferrer" title="${tip}">${label}</a>`
        : `<a title="${tip}" style="cursor:default">${label}</a>`;
    }).join('');
  } else {
    provEl.innerHTML = '';
  }
}

// ── 인용 검증 스트립 ──

/**
 * 답변 아래에 인용 검증(✓ 근거 확인 / ⚠ 미확인) 스트립을 그린다.
 * report 가 null 이면(인용 없음) 아무것도 안 그린다.
 */
function renderCitations(bubbleId, report) {
  const bubble = document.getElementById(bubbleId);
  if (!bubble) return;

  const existing = bubble.querySelector('.citation-strip');
  if (existing) existing.remove();
  if (!report) return;

  const chips = report.items.map(it => {
    const mark = it.verified ? '✓' : '⚠';
    const cls = it.verified ? 'citation-chip' : 'citation-chip citation-chip--unverified';
    // label 은 문서 내용(신뢰 불가) → 반드시 escape
    return `<span class="${cls}"><span class="cite-mark">${mark}</span>${escapeHtml(it.label)}</span>`;
  }).join('');

  const strip = document.createElement('div');
  strip.className = `citation-strip citation-strip--${report.tone}`;
  strip.innerHTML = `
    <div class="citation-summary">${escapeHtml(report.summary)}</div>
    <div class="citation-chips">${chips}</div>
  `;
  bubble.appendChild(strip);

  const history = document.getElementById('chat-history');
  history.scrollTop = history.scrollHeight;
}

// ── 인라인 그래프 ──

function renderInlineGraph(bubbleId, graphData) {
  const bubble = document.getElementById(bubbleId);
  if (!bubble) return;

  // 기존 그래프 제거
  const existing = bubble.querySelector('.chat-inline-graph');
  if (existing) existing.remove();

  const graphDiv = document.createElement('div');
  graphDiv.className = 'chat-inline-graph';
  bubble.appendChild(graphDiv);

  // vis-network 렌더링
  const nodes = new vis.DataSet();
  const edges = new vis.DataSet();
  const nodeSet = new Set();

  // center 노드
  if (graphData.center) {
    nodes.add({ id: graphData.center, label: graphData.center, color: { background: '#2272c4', border: '#8fdcff' }, font: { color: '#ffffff', strokeWidth: 3, strokeColor: '#070d1d' } });
    nodeSet.add(graphData.center);
  }

  // designed edges
  for (const e of (graphData.designed_edges || [])) {
    if (!nodeSet.has(e.from)) { nodes.add({ id: e.from, label: e.from, font: { color: '#eaf1fb', strokeWidth: 3, strokeColor: '#070d1d' } }); nodeSet.add(e.from); }
    if (!nodeSet.has(e.to)) { nodes.add({ id: e.to, label: e.to, font: { color: '#eaf1fb', strokeWidth: 3, strokeColor: '#070d1d' } }); nodeSet.add(e.to); }
    edges.add({
      from: e.from, to: e.to,
      label: e.type, arrows: 'to',
      color: { color: '#4fb6ee' },
      width: Math.max(1, (e.confidence || 0.5) * 3),
      font: { color: '#dbe7f5', size: 10, background: 'rgba(9,15,32,0.82)' },
    });
  }

  // observed edges
  for (const o of (graphData.observed_edges || [])) {
    if (!nodeSet.has(o.from)) { nodes.add({ id: o.from, label: o.from, font: { color: '#eaf1fb', strokeWidth: 3, strokeColor: '#070d1d' } }); nodeSet.add(o.from); }
    if (!nodeSet.has(o.to)) { nodes.add({ id: o.to, label: o.to, font: { color: '#eaf1fb', strokeWidth: 3, strokeColor: '#070d1d' } }); nodeSet.add(o.to); }
    const color = (o.error_rate || 0) > 0.05 ? '#f87a85' : '#eaa44e';
    edges.add({
      from: o.from, to: o.to,
      label: `${o.type} (${o.call_count || 0})`,
      arrows: 'to', dashes: true,
      color: { color },
      font: { color: '#dbe7f5', size: 10, background: 'rgba(9,15,32,0.82)' },
    });
  }

  const net = new vis.Network(graphDiv, { nodes, edges }, {
    physics: {
      solver: 'barnesHut',
      barnesHut: { gravitationalConstant: -4200, springLength: 120, springConstant: 0.04, avoidOverlap: 0.55 },
      stabilization: { iterations: 120 },
    },
    nodes: {
      shape: 'dot', size: 16,
      color: { background: '#111d3a', border: '#4fb6ee' },
      borderWidth: 2,
    },
    edges: { smooth: { type: 'curvedCW', roundness: 0.1 } },
    interaction: { zoomView: false },
    layout: { improvedLayout: true },
  });
  // 안정화 후 물리를 멈추고(떨림 제거) 모든 노드가 박스 안에 들어오도록 맞춘다.
  net.once('stabilizationIterationsDone', () => {
    net.setOptions({ physics: false });
    net.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
  });
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

export function destroy() {
  // cleanup if needed
}

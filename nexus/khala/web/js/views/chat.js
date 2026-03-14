/**
 * 채팅 뷰.
 * SSE 스트리밍 답변 + Evidence 패널 + 인라인 그래프.
 */

import { streamAnswer, suggestEntities } from '../api.js';
import { renderMarkdown } from '../components/markdown.js';
import { showToast } from '../components/toast.js';

let chatHistory = [];
let isStreaming = false;
let autocompleteTimer = null;
let autocompleteIndex = -1;
let autocompleteItems = [];

export function render(container) {
  container.innerHTML = `
    <div class="chat-layout">
      <div class="chat-main">
        <div class="chat-history" id="chat-history">
          <div class="chat-empty" id="chat-empty">
            <div class="chat-empty-title">Khala</div>
            <div class="chat-empty-hint">조직의 문서와 운영 데이터를 검색합니다</div>
            <div class="chat-empty-hint" style="color:var(--text-muted)">@서비스명으로 엔티티를 지정할 수 있습니다</div>
          </div>
        </div>
        <div class="chat-input-area">
          <div class="chat-input-wrapper" style="position:relative">
            <div class="autocomplete-dropdown" id="autocomplete-dropdown"></div>
            <textarea id="chat-input" rows="1"
              placeholder="검색어를 입력하세요... @서비스명으로 엔티티 지정"
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
}

function bindEvents() {
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');

  sendBtn.addEventListener('click', () => submitQuery());

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
  dropdown.innerHTML = items.map((item, i) => `
    <div class="autocomplete-item" data-index="${i}">
      <span class="ac-type">${item.type}</span>
      <span class="ac-name">${item.name}</span>
      <span class="ac-desc">${item.description || ''}</span>
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
        updateBubble(bubbleId, fullAnswer, false);
        // 히스토리 업데이트
        const entry = chatHistory.find(h => h.id === bubbleId);
        if (entry) entry.content = fullAnswer;
      },
      onError(data) {
        showToast(data.error || '스트리밍 에러', 'error');
        updateBubble(bubbleId, fullAnswer || '오류가 발생했습니다.', false);
      },
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

function appendBubble(role, content, id = null, streaming = false) {
  const history = document.getElementById('chat-history');
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}`;
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
      appendBubble('user', msg.content);
    } else {
      appendBubble('assistant', msg.content, msg.id);
    }
  }
}

// ── Evidence 패널 ──

function renderEvidence(snippets, provenance) {
  const panel = document.getElementById('evidence-panel');
  panel.classList.remove('hidden');

  document.getElementById('evidence-count').textContent = `${snippets.length}건`;

  const list = document.getElementById('evidence-list');
  list.innerHTML = snippets.map((s, i) => `
    <div class="evidence-item" title="${s.source_uri || ''}">
      <div>
        <span class="ev-index">${i + 1}</span>
        <span class="ev-title">${escapeHtml(s.doc_title || '(제목 없음)')}</span>
      </div>
      <div class="ev-path">${escapeHtml(s.section_path || '')}</div>
      <div class="ev-text">${escapeHtml(s.text || '')}</div>
      <div class="ev-score">score: ${(s.score || 0).toFixed(4)}</div>
    </div>
  `).join('');

  const provEl = document.getElementById('evidence-provenance');
  if (provenance.length > 0) {
    provEl.innerHTML = `
      <h4>출처</h4>
      ${provenance.map(p =>
        `<a href="#" title="${p.source_version || ''}">${escapeHtml(p.source_uri || p.doc_rid)}</a>`
      ).join('')}
    `;
  } else {
    provEl.innerHTML = '';
  }
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
    nodes.add({ id: graphData.center, label: graphData.center, color: '#6c8cff', font: { color: '#e4e6eb' } });
    nodeSet.add(graphData.center);
  }

  // designed edges
  for (const e of (graphData.designed_edges || [])) {
    if (!nodeSet.has(e.from)) { nodes.add({ id: e.from, label: e.from, font: { color: '#e4e6eb' } }); nodeSet.add(e.from); }
    if (!nodeSet.has(e.to)) { nodes.add({ id: e.to, label: e.to, font: { color: '#e4e6eb' } }); nodeSet.add(e.to); }
    edges.add({
      from: e.from, to: e.to,
      label: e.type, arrows: 'to',
      color: { color: '#60a5fa' },
      width: Math.max(1, (e.confidence || 0.5) * 3),
      font: { color: '#9ca3b0', size: 10 },
    });
  }

  // observed edges
  for (const o of (graphData.observed_edges || [])) {
    if (!nodeSet.has(o.from)) { nodes.add({ id: o.from, label: o.from, font: { color: '#e4e6eb' } }); nodeSet.add(o.from); }
    if (!nodeSet.has(o.to)) { nodes.add({ id: o.to, label: o.to, font: { color: '#e4e6eb' } }); nodeSet.add(o.to); }
    const color = (o.error_rate || 0) > 0.05 ? '#f87171' : '#fb923c';
    edges.add({
      from: o.from, to: o.to,
      label: `${o.type} (${o.call_count || 0})`,
      arrows: 'to', dashes: true,
      color: { color },
      font: { color: '#9ca3b0', size: 10 },
    });
  }

  new vis.Network(graphDiv, { nodes, edges }, {
    physics: { stabilization: { iterations: 50 } },
    nodes: {
      shape: 'dot', size: 16,
      color: { background: '#242736', border: '#6c8cff' },
      borderWidth: 2,
    },
    edges: { smooth: { type: 'curvedCW', roundness: 0.1 } },
    interaction: { zoomView: false },
    layout: { improvedLayout: true },
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

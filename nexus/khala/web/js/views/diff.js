/**
 * Diff 대시보드 뷰.
 */

import { getDiff } from '../api.js';
import { showToast } from '../components/toast.js';

let currentFilter = null;
let entityFilter = '';
let filterTimer = null;

export function render(container) {
  container.innerHTML = `
    <div class="diff-layout">
      <h2 style="margin-bottom:16px">설계-관측 Diff</h2>
      <div class="diff-summary" id="diff-summary"></div>
      <div class="diff-filters">
        <button class="diff-filter-btn active" data-filter="">전체</button>
        <button class="diff-filter-btn" data-filter="doc_only">문서에만 존재</button>
        <button class="diff-filter-btn" data-filter="observed_only">관측에만 존재</button>
        <button class="diff-filter-btn" data-filter="conflict">불일치</button>
        <input type="text" class="diff-entity-input" id="diff-entity-input"
          placeholder="엔티티 필터...">
      </div>
      <div class="diff-list" id="diff-list"></div>
    </div>
  `;

  // 필터 버튼
  container.querySelectorAll('.diff-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.diff-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter || null;
      loadDiff();
    });
  });

  // 엔티티 필터
  document.getElementById('diff-entity-input').addEventListener('input', (e) => {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => {
      entityFilter = e.target.value.trim();
      loadDiff();
    }, 300);
  });

  currentFilter = null;
  entityFilter = '';
  loadDiff();
}

async function loadDiff() {
  try {
    const { data } = await getDiff({
      flag_filter: currentFilter,
      entity_filter: entityFilter || null,
    });
    renderSummary(data);
    renderList(data.diffs || []);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderSummary(data) {
  const diffs = data.diffs || [];
  const counts = { doc_only: 0, observed_only: 0, conflict: 0 };
  for (const d of diffs) {
    if (counts[d.flag] !== undefined) counts[d.flag]++;
  }

  document.getElementById('diff-summary').innerHTML = `
    <div class="diff-card doc-only">
      <div class="diff-count">${counts.doc_only}</div>
      <div class="diff-label">문서에만 존재</div>
    </div>
    <div class="diff-card observed-only">
      <div class="diff-count">${counts.observed_only}</div>
      <div class="diff-label">관측에만 존재</div>
    </div>
    <div class="diff-card conflict">
      <div class="diff-count">${counts.conflict}</div>
      <div class="diff-label">불일치</div>
    </div>
  `;
}

function renderList(diffs) {
  const list = document.getElementById('diff-list');
  if (diffs.length === 0) {
    list.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:24px">불일치 항목이 없습니다</p>`;
    return;
  }

  const flagLabels = {
    doc_only: '문서에만',
    observed_only: '관측에만',
    conflict: '불일치',
  };

  list.innerHTML = diffs.map(d => `
    <div class="diff-item">
      <div class="diff-item-header">
        <span class="diff-flag ${d.flag}">${flagLabels[d.flag] || d.flag}</span>
        <span class="diff-relation">${escapeHtml(d.from_name)} → ${escapeHtml(d.to_name)}</span>
        <span style="margin-left:auto;font-size:12px;color:var(--text-muted)">${d.edge_type || ''}</span>
      </div>
      <div class="diff-detail">${escapeHtml(d.detail || '')}</div>
      ${renderEvidence(d)}
    </div>
  `).join('');
}

function renderEvidence(d) {
  let html = '';

  if (d.designed_evidence && d.designed_evidence.length > 0) {
    html += `<div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">`;
    html += `<strong>설계 근거:</strong> `;
    html += d.designed_evidence.map(e =>
      `${escapeHtml(e.doc_title)} (${escapeHtml(e.section_path)})`
    ).join(', ');
    html += `</div>`;
  }

  if (d.observed_evidence && d.observed_evidence.sample_trace_ids) {
    html += `<div style="margin-top:4px;font-size:12px;color:var(--text-secondary)">`;
    html += `<strong>관측 근거:</strong> `;
    html += `trace: ${d.observed_evidence.sample_trace_ids.slice(0, 2).join(', ')}`;
    html += `</div>`;
  }

  return html;
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

export function destroy() {}

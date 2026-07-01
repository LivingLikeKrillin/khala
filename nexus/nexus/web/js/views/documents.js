/**
 * 문서 브라우저 뷰.
 * 행 클릭 → 상세 드로어(메타데이터 + 출처 포인터). Nexus는 인덱스지 저장소가
 * 아니므로 원본 "내용"이 아니라 source_uri 포인터로 연결/표시한다.
 */

import { listDocuments } from '../api.js';
import { trustSignal } from '../doctype-signal.js';
import { showToast } from '../components/toast.js';

let currentOffset = 0;
let currentLimit = 20;
let totalDocs = 0;
let currentDocs = [];

export function render(container) {
  container.innerHTML = `
    <div class="documents-layout">
      <div class="documents-header">
        <h2>인덱싱된 문서</h2>
      </div>
      <div class="documents-scroll">
        <table class="doc-table">
          <thead>
            <tr>
              <th>제목</th>
              <th>타입</th>
              <th>분류</th>
              <th>언어</th>
              <th>청크</th>
              <th>업데이트</th>
            </tr>
          </thead>
          <tbody id="doc-tbody"></tbody>
        </table>
      </div>
      <div class="doc-pagination">
        <button id="doc-prev">이전</button>
        <span id="doc-page-info"></span>
        <button id="doc-next">다음</button>
      </div>
      <aside class="doc-detail-panel hidden" id="doc-detail-panel" aria-label="문서 상세">
        <div class="doc-detail-head">
          <span class="doc-detail-eyebrow">DOCUMENT</span>
          <button class="doc-detail-close" id="doc-detail-close" type="button" aria-label="닫기">✕</button>
        </div>
        <div id="doc-detail-content"></div>
      </aside>
    </div>
  `;

  document.getElementById('doc-prev').addEventListener('click', () => {
    if (currentOffset >= currentLimit) {
      currentOffset -= currentLimit;
      loadDocs();
    }
  });
  document.getElementById('doc-next').addEventListener('click', () => {
    if (currentOffset + currentLimit < totalDocs) {
      currentOffset += currentLimit;
      loadDocs();
    }
  });

  // 행 클릭 → 상세 드로어 (이벤트 위임)
  document.getElementById('doc-tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-idx]');
    if (!tr) return;
    const doc = currentDocs[Number(tr.dataset.idx)];
    if (doc) showDocDetail(doc);
  });
  document.getElementById('doc-detail-close').addEventListener('click', hideDocDetail);

  currentOffset = 0;
  loadDocs();
}

async function loadDocs() {
  try {
    const { data, meta } = await listDocuments({ offset: currentOffset, limit: currentLimit });
    totalDocs = meta.total || 0;
    currentDocs = data || [];
    renderTable(currentDocs);
    updatePagination();
    hideDocDetail();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderTable(docs) {
  const tbody = document.getElementById('doc-tbody');
  if (!docs || docs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="doc-empty">문서가 없습니다</td></tr>`;
    return;
  }
  tbody.innerHTML = docs
    .map((d, i) => {
      const t = trustSignal(d.doc_type);
      return `
    <tr data-idx="${i}" class="doc-row">
      <td class="doc-title-cell">${escapeHtml(d.title || '(제목 없음)')}</td>
      <td><span class="doc-type-badge trust-badge--${t.tone}" title="${escapeHtml(t.label + ' · ' + t.note)}">${escapeHtml(d.doc_type || '-')}</span></td>
      <td>${escapeHtml(d.classification || '-')}</td>
      <td>${escapeHtml(d.language || '-')}</td>
      <td class="doc-num">${d.chunk_count ?? 0}</td>
      <td class="doc-num">${d.updated_at ? formatDate(d.updated_at) : '-'}</td>
    </tr>`;
    })
    .join('');
}

function showDocDetail(doc) {
  const panel = document.getElementById('doc-detail-panel');
  const t = trustSignal(doc.doc_type);
  const rows = [
    ['타입', `<span class="doc-type-badge trust-badge--${t.tone}">${escapeHtml(doc.doc_type || '-')}</span> <span class="doc-detail-note">${escapeHtml(t.label)}</span>`],
    ['분류', escapeHtml(doc.classification || '-')],
    ['언어', escapeHtml(doc.language || '-')],
    ['청크', `${doc.chunk_count ?? 0}`],
    ['버전', escapeHtml(doc.source_version || '-')],
    ['업데이트', doc.updated_at ? escapeHtml(formatDate(doc.updated_at)) : '-'],
  ];
  document.getElementById('doc-detail-content').innerHTML = `
    <h3 class="doc-detail-title">${escapeHtml(doc.title || '(제목 없음)')}</h3>
    <dl class="doc-detail-meta">
      ${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}
    </dl>
    <div class="doc-detail-source">
      <span class="doc-detail-eyebrow">SOURCE</span>
      ${sourceLink(doc.source_uri)}
    </div>
    <p class="doc-detail-hint">Nexus는 원본을 저장하지 않고 색인만 보관합니다. 원본은 출처에서 확인하세요.</p>
  `;
  panel.classList.remove('hidden');
}

function hideDocDetail() {
  const panel = document.getElementById('doc-detail-panel');
  if (panel) panel.classList.add('hidden');
}

function sourceLink(uri) {
  if (!uri) return '<span class="doc-detail-note">출처 정보 없음</span>';
  if (/^https?:\/\//i.test(uri)) {
    return `<a class="doc-detail-link" href="${escapeAttr(uri)}" target="_blank" rel="noopener">${escapeHtml(uri)} ↗</a>`;
  }
  return `<code class="doc-detail-uri">${escapeHtml(uri)}</code>`;
}

function updatePagination() {
  const page = Math.floor(currentOffset / currentLimit) + 1;
  const totalPages = Math.max(1, Math.ceil(totalDocs / currentLimit));
  document.getElementById('doc-page-info').textContent = `${page} / ${totalPages} (총 ${totalDocs}건)`;
  document.getElementById('doc-prev').disabled = currentOffset === 0;
  document.getElementById('doc-next').disabled = currentOffset + currentLimit >= totalDocs;
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  } catch {
    return iso;
  }
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function escapeAttr(str) {
  return String(str).replace(/"/g, '&quot;');
}

export function destroy() {}

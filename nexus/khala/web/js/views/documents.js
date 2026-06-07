/**
 * 문서 브라우저 뷰.
 */

import { listDocuments } from '../api.js';
import { showToast } from '../components/toast.js';

let currentOffset = 0;
let currentLimit = 20;
let totalDocs = 0;

export function render(container) {
  container.innerHTML = `
    <div class="documents-layout">
      <div class="documents-header">
        <h2>인덱싱된 문서</h2>
      </div>
      <div style="flex:1; overflow-y:auto;">
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

  currentOffset = 0;
  loadDocs();
}

async function loadDocs() {
  try {
    const { data, meta } = await listDocuments({ offset: currentOffset, limit: currentLimit });
    totalDocs = meta.total || 0;
    renderTable(data);
    updatePagination();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderTable(docs) {
  const tbody = document.getElementById('doc-tbody');
  if (!docs || docs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">문서가 없습니다</td></tr>`;
    return;
  }
  tbody.innerHTML = docs.map(d => `
    <tr>
      <td class="doc-title-cell">${escapeHtml(d.title || '(제목 없음)')}</td>
      <td><span class="doc-type-badge">${d.doc_type || '-'}</span></td>
      <td>${d.classification || '-'}</td>
      <td>${d.language || '-'}</td>
      <td>${d.chunk_count ?? 0}</td>
      <td>${d.updated_at ? formatDate(d.updated_at) : '-'}</td>
    </tr>
  `).join('');
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
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  } catch {
    return iso;
  }
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

export function destroy() {}

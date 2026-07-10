/**
 * 문서 브라우저 — 보고, 찾고, 어디서 왔는지 알고, 숨기고, 되돌린다.
 * SPEC-nexus-document-lifecycle §4.5.
 *
 * 파괴적 동작에는 반드시 문장이 붙는다. 문장 없는 파괴 버튼이 `supersede` 가 그 꼴로
 * 출시된 이유다.
 */

import {
  hideDocument, listDocuments, restoreDocument, unsupersedeDocument,
} from '../api.js';
import { showToast } from '../components/toast.js';
import { trustSignal } from '../doctype-signal.js';

const LIMIT = 20;
let offset = 0;
let query = '';
let statusFilter = 'active';
let debounce = null;

export function destroy() {
  if (debounce) { clearTimeout(debounce); debounce = null; }
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

const ORIGIN_LABEL = { notion: 'Notion', upload: '업로드', file: '파일' };

// 같은 행, 다른 원인, 다른 문장. pruned 문서는 페이지가 돌아오면 스스로 되살아나고,
// 숨긴 문서는 절대 되살아나지 않는다 — 사용자에게 같은 말을 하면 거짓말이 된다.
const STATUS_NOTE = {
  hidden: '직접 숨긴 문서입니다. 동기화가 되살리지 않습니다.',
  pruned: 'Notion 에서 사라져 내려간 문서입니다. 페이지가 돌아오면 다음 동기화가 되살립니다.',
  superseded: '다른 문서로 대체되었습니다.',
};

export function render(container) {
  offset = 0; query = ''; statusFilter = 'active';
  container.innerHTML = `
    <div class="documents-layout">
      <div class="documents-header">
        <h2>인덱싱된 문서</h2>
        <div class="doc-controls">
          <input id="doc-q" type="search" placeholder="제목 검색" autocomplete="off">
          <select id="doc-status">
            <option value="active">검색에 노출 중</option>
            <option value="hidden">숨김</option>
            <option value="pruned">Notion 에서 삭제됨</option>
            <option value="superseded">대체됨</option>
            <option value="all">전체</option>
          </select>
        </div>
      </div>
      <div id="doc-note" class="doc-note hidden"></div>
      <div class="doc-table-wrap">
        <table class="doc-table">
          <thead>
            <tr>
              <th>제목</th><th>출처</th><th>타입</th><th>분류</th>
              <th>청크</th><th>업데이트</th><th></th>
            </tr>
          </thead>
          <tbody id="doc-tbody"></tbody>
        </table>
      </div>
      <div id="doc-pager" class="doc-pager"></div>
      <div id="doc-confirm"></div>
    </div>
  `;

  document.getElementById('doc-q').addEventListener('input', (e) => {
    clearTimeout(debounce);
    const v = e.target.value.trim();
    debounce = setTimeout(() => { query = v; offset = 0; load(); }, 250);
  });
  document.getElementById('doc-status').addEventListener('change', (e) => {
    statusFilter = e.target.value; offset = 0; load();
  });

  load();
}

async function load() {
  const tbody = document.getElementById('doc-tbody');
  if (!tbody) return;                      // 뷰가 이미 떠났다
  tbody.innerHTML = '<tr><td colspan="7" class="doc-empty">불러오는 중…</td></tr>';

  const note = document.getElementById('doc-note');
  const text = STATUS_NOTE[statusFilter];
  note.classList.toggle('hidden', !text);
  if (text) note.textContent = text;

  try {
    const { data } = await listDocuments({ q: query, status: statusFilter, offset, limit: LIMIT });
    renderTable(data.documents);
    renderPager(data.total);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="doc-empty">${esc(err.message)}</td></tr>`;
    showToast(err.message, 'error');
  }
}

function originCell(d) {
  const label = ORIGIN_LABEL[d.origin] || d.origin;
  return d.origin_url
    ? `<a class="doc-origin" href="${esc(d.origin_url)}" target="_blank" rel="noopener">${esc(label)} ↗</a>`
    : `<span class="doc-origin" title="${esc(d.source_uri)}">${esc(label)}</span>`;
}

function actionsFor(d) {
  if (d.status === 'superseded') {
    return `<button class="btn-ghost" data-unsupersede="${esc(d.rid)}" data-title="${esc(d.title)}">supersession 취소</button>`;
  }
  if (d.status === 'hidden' || d.status === 'pruned') {
    return `<button class="btn-ghost" data-restore="${esc(d.rid)}">되돌리기</button>`;
  }
  return `<button class="btn-ghost" data-hide="${esc(d.rid)}" data-title="${esc(d.title)}">숨기기</button>`;
}

function renderTable(docs) {
  const tbody = document.getElementById('doc-tbody');
  if (!docs || docs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="doc-empty">문서가 없습니다</td></tr>';
    return;
  }
  tbody.innerHTML = docs.map((d) => {
    const t = trustSignal(d.doc_type);
    const dim = d.status !== 'active' ? ' class="doc-row-dim"' : '';
    // superseded 행은 무엇이 자기를 대체했는지 말한다 — rid 가 아니라 제목으로
    const by = d.status === 'superseded' && d.superseded_by
      ? `<div class="doc-superseded-by">→ ${esc(d.superseded_by_title || d.superseded_by)}</div>`
      : '';
    return `<tr${dim}>
      <td class="doc-title-cell">${esc(d.title || '(제목 없음)')}${by}</td>
      <td>${originCell(d)}</td>
      <td><span class="doc-type-badge trust-badge--${esc(t.tone)}" title="${esc(`${t.label} · ${t.note}`)}">${esc(d.doc_type || '-')}</span></td>
      <td>${esc(d.classification || '-')}</td>
      <td>${d.chunk_count ?? 0}</td>
      <td>${esc((d.updated_at || '').slice(0, 10))}</td>
      <td class="doc-actions">${actionsFor(d)}</td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('[data-hide]').forEach((b) =>
    b.addEventListener('click', () => confirmHide(b.dataset.hide, b.dataset.title)));
  tbody.querySelectorAll('[data-restore]').forEach((b) =>
    b.addEventListener('click', () => doRestore(b.dataset.restore)));
  tbody.querySelectorAll('[data-unsupersede]').forEach((b) =>
    b.addEventListener('click', () => confirmUnsupersede(b.dataset.unsupersede, b.dataset.title)));
}

function renderPager(total) {
  const pager = document.getElementById('doc-pager');
  const page = Math.floor(offset / LIMIT) + 1;
  const pages = Math.max(1, Math.ceil(total / LIMIT));
  pager.innerHTML = `
    <button class="btn-ghost" id="doc-prev" ${offset === 0 ? 'disabled' : ''}>이전</button>
    <span class="doc-page-info">${page} / ${pages} (총 ${total}건)</span>
    <button class="btn-ghost" id="doc-next" ${offset + LIMIT >= total ? 'disabled' : ''}>다음</button>`;
  document.getElementById('doc-prev').addEventListener('click', () => { offset -= LIMIT; load(); });
  document.getElementById('doc-next').addEventListener('click', () => { offset += LIMIT; load(); });
}

/** 파괴적이다. 무슨 일이 일어나는지 문장으로 말하고 나서 묻는다. */
function confirmHide(rid, title) {
  const box = document.getElementById('doc-confirm');
  box.innerHTML = `<div class="doc-confirm-card">
      <div class="doc-confirm-title">「${esc(title)}」을 숨길까요?</div>
      <div class="doc-confirm-body">
        검색에서 사라집니다. 문서와 청크는 지워지지 않으며 언제든 되돌릴 수 있습니다.
      </div>
      <div class="doc-confirm-actions">
        <button class="btn-ghost" id="dc-cancel">취소</button>
        <button class="btn-danger" id="dc-ok">숨기기</button>
      </div>
    </div>`;
  document.getElementById('dc-cancel').addEventListener('click', () => { box.innerHTML = ''; });
  document.getElementById('dc-ok').addEventListener('click', async () => {
    box.innerHTML = '';
    try {
      await hideDocument(rid);
      showToast('숨겼습니다. 상태 필터에서 되돌릴 수 있습니다.', 'success');
      load();
    } catch (err) { showToast(err.message, 'error'); }
  });
}

function confirmUnsupersede(rid, title) {
  const box = document.getElementById('doc-confirm');
  box.innerHTML = `<div class="doc-confirm-card">
      <div class="doc-confirm-title">「${esc(title)}」의 supersession 을 취소할까요?</div>
      <div class="doc-confirm-body">
        이 문서가 다시 검색에 나타납니다. 대체한 문서가 아직 살아 있다면 둘이 공존하게 됩니다.
      </div>
      <input id="dc-reason" type="text" placeholder="사유 (필수)" autocomplete="off">
      <div class="doc-confirm-actions">
        <button class="btn-ghost" id="dc-cancel">취소</button>
        <button class="btn-danger" id="dc-ok">supersession 취소</button>
      </div>
    </div>`;
  document.getElementById('dc-cancel').addEventListener('click', () => { box.innerHTML = ''; });
  document.getElementById('dc-ok').addEventListener('click', async () => {
    const reason = document.getElementById('dc-reason').value.trim();
    if (!reason) { showToast('사유가 필요합니다', 'error'); return; }
    try {
      await unsupersedeDocument(rid, reason);
      box.innerHTML = '';
      showToast('되돌렸습니다', 'success');
      load();
    } catch (err) {
      // 409 chain_broken — 어느 문서가 막고 있는지 서버가 이름으로 알려준다
      showToast(err.message, 'error');
    }
  });
}

async function doRestore(rid) {
  try {
    await restoreDocument(rid);
    showToast('되돌렸습니다', 'success');
    load();
  } catch (err) { showToast(err.message, 'error'); }
}

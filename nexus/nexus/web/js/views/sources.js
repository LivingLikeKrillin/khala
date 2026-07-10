/**
 * 소스(Notion) 관리 뷰 — SPEC-nexus-notion-source-console §4.8.
 *
 * 사람이 여기서 하는 일: 페이지 URL 붙여넣기 → 동기화 → 사라진 문서 확인 → 확정.
 * 터미널을 열지 않는다. 같은 엔드포인트를 MCP 에이전트도 쓴다.
 */

import { addSource, getLatestSync, getSyncRun, listSources, removeSource, sourcesHealth, startSync } from '../api.js';
import { showToast } from '../components/toast.js';

let _pollTimer = null;

export function destroy() {
  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function render(container) {
  container.innerHTML = `
    <div class="sources-layout">
      <header class="sources-head">
        <h2>소스</h2>
        <p class="sources-sub">Notion 페이지를 연결하면 그 하위 트리 전체가 검색에 들어옵니다.</p>
      </header>

      <section class="sources-add">
        <input id="src-url" type="text" placeholder="Notion 페이지 URL 붙여넣기" autocomplete="off">
        <input id="src-label" type="text" placeholder="이름 (선택)" autocomplete="off">
        <button id="src-add" class="btn-primary">추가</button>
      </section>

      <!-- 연결 상태. 토큰이 정상이면 integration·워크스페이스를, 아니면 무엇이 잘못됐는지 말한다. -->
      <section id="src-token-warn" class="sources-conn">연결 상태 확인 중…</section>

      <section id="src-list" class="sources-list"></section>

      <section class="sources-actions">
        <button id="src-preview" class="btn-secondary">삭제 반영 미리보기</button>
        <button id="src-sync" class="btn-primary">지금 동기화</button>
      </section>

      <section id="src-run" class="sources-run"></section>
    </div>
  `;

  document.getElementById('src-add').addEventListener('click', onAdd);
  document.getElementById('src-url').addEventListener('keydown', (e) => { if (e.key === 'Enter') onAdd(); });
  document.getElementById('src-sync').addEventListener('click', () => onSync({ reconcile: false }));
  document.getElementById('src-preview').addEventListener('click', () => onSync({ reconcile: true, dryRun: true }));

  refreshList();
  showLatestRun();
}

// 상태 → 사람이 읽을 문장. `unknown` 은 초록도 빨강도 아니다 — 모른다는 뜻이다.
const TOKEN_PROSE = {
  ok: null,   // 패널에 integration·워크스페이스를 대신 보여준다
  invalid: '토큰이 거부되었습니다(401). 폐기되었거나 잘못된 값입니다 — .env 의 NOTION_TOKEN 을 확인하세요.',
  not_configured: 'Notion 토큰이 서버에 설정되지 않았습니다 — 동기화할 수 없습니다.',
  unknown: 'Notion 에 연결할 수 없어 토큰을 확인하지 못했습니다.',
};
const ROOT_PROSE = {
  reachable: '도달 가능', unreachable: '볼 수 없음',
  invalid_id: 'id 형식 오류', unknown: '확인하지 못함',
};

async function refreshList() {
  const el = document.getElementById('src-list');
  el.innerHTML = '<div class="sources-loading">불러오는 중…</div>';
  try {
    const { data } = await listSources();

    if (!data.roots.length) {
      el.innerHTML = `<div class="sources-empty">
        연결된 Notion 페이지가 없습니다. 위에 페이지 URL을 붙여넣어 시작하세요.
      </div>`;
    } else {
      el.innerHTML = data.roots.map((r) => `
        <div class="sources-row">
          <div class="sources-row-main">
            <div class="sources-row-label">${esc(r.label || r.root_id)}</div>
            <div class="sources-row-id">${esc(r.root_id)}</div>
            <div class="sources-row-state" data-state-for="${esc(r.root_id)}">확인 중…</div>
          </div>
          <button class="btn-ghost" data-remove="${esc(r.root_id)}">연결 해제</button>
        </div>
      `).join('');

      el.querySelectorAll('[data-remove]').forEach((b) =>
        b.addEventListener('click', () => onRemove(b.dataset.remove)));
    }

    // 외부 API 를 때리므로 목록 렌더를 막지 않는다. 결과가 오면 채운다.
    refreshHealth();
  } catch (e) {
    el.innerHTML = `<div class="sources-empty">목록을 불러오지 못했습니다: ${esc(e.message)}</div>`;
    showToast(e.message, 'error');
  }
}

/** Notion 에게 직접 물어 토큰과 각 root 의 상태를 채운다. 실패해도 목록은 살아 있다. */
async function refreshHealth() {
  const warn = document.getElementById('src-token-warn');
  try {
    const { data } = await sourcesHealth();
    const t = data.token;

    if (t.state === 'ok') {
      warn.className = 'sources-conn';
      warn.innerHTML = `<strong>${esc(t.integration || 'integration')}</strong>
        · ${esc(t.workspace || '')}
        <span class="sources-conn-prefix">${esc(t.prefix)}…</span>`;
    } else {
      warn.className = 'sources-warn';
      warn.textContent = TOKEN_PROSE[t.state] || '토큰 상태를 알 수 없습니다.';
    }

    for (const r of data.roots) {
      const cell = document.querySelector(`[data-state-for="${CSS.escape(r.root_id)}"]`);
      if (!cell) continue;
      cell.className = `sources-row-state state-${esc(r.state)}`;
      cell.textContent = r.remedy
        ? `${ROOT_PROSE[r.state] || r.state} — ${r.remedy}`
        : `${ROOT_PROSE[r.state] || r.state}${r.title ? ` · ${r.title}` : ''}`;
    }
  } catch (e) {
    // 403(capability 없음)도 여기로 온다. 초록으로 칠하지 않는다 — 못 봤을 뿐이다.
    warn.className = 'sources-warn';
    warn.textContent = `연결 상태를 확인하지 못했습니다: ${e.message}`;
    document.querySelectorAll('[data-state-for]').forEach((c) => { c.textContent = '확인하지 못함'; });
  }
}

async function onAdd() {
  const url = document.getElementById('src-url').value.trim();
  if (!url) return;
  try {
    const { data } = await addSource(url, document.getElementById('src-label').value.trim());
    document.getElementById('src-url').value = '';
    document.getElementById('src-label').value = '';
    if (data.state === 'unreachable' || data.state === 'invalid_id') {
      // 등록은 됐다. 다만 지금은 닿지 않는다 — 동기화를 돌려 봐야 알던 것을 여기서 말한다.
      showToast(`등록했지만 지금은 볼 수 없습니다. ${data.remedy}`, 'error');
    } else if (data.state === 'unknown') {
      showToast('등록했습니다. 지금은 Notion 에 물어볼 수 없어 도달 여부를 확인하지 못했습니다.', 'info');
    } else {
      showToast(`연결됨: ${data.title || data.root_id}`, 'success');
    }
    refreshList();
  } catch (e) {
    showToast(e.message, 'error');   // 409 중복 · 400 파싱 실패 · 403 권한
  }
}

async function onRemove(rootId) {
  try {
    await removeSource(rootId);
    // 문서는 남는다. 걷지 않게 될 뿐이다 — 사용자가 오해하지 않도록 말해준다.
    showToast('연결을 해제했습니다. 이미 색인된 문서는 그대로 남습니다.', 'success');
    refreshList();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function onSync(opts) {
  try {
    const { data } = await startSync(opts);
    showToast('동기화를 시작했습니다', 'success');
    pollRun(data.run_id);
  } catch (e) {
    showToast(e.message, 'error');   // 409 이미 실행 중 · 503 토큰 없음 · 400 root 없음
  }
}

async function confirmPlan(runId) {
  try {
    const { data } = await startSync({ confirmPlan: runId });
    showToast('적용을 시작했습니다', 'success');
    pollRun(data.run_id);
  } catch (e) {
    // 409 plan_stale — 미리보기 이후 Notion 이 바뀌었다. 아무것도 적용되지 않았다.
    showToast(e.message, 'error');
  }
}

async function showLatestRun() {
  try {
    const { data } = await getLatestSync();
    renderRun(data);
    if (data.status === 'running') pollRun(data.run_id);
  } catch {
    /* 아직 실행 이력 없음 — 정상 */
  }
}

function pollRun(runId) {
  destroy();
  const tick = async () => {
    try {
      const { data } = await getSyncRun(runId);
      renderRun(data);
      if (data.status === 'running') _pollTimer = setTimeout(tick, 1500);
    } catch (e) {
      showToast(e.message, 'error');
    }
  };
  tick();
}

function renderRun(run) {
  const el = document.getElementById('src-run');
  if (!el) return;                   // 뷰가 이미 떠났다

  const c = run.counts || {};
  const badge = {
    running: '<span class="run-badge running">진행 중</span>',
    succeeded: '<span class="run-badge ok">완료</span>',
    failed: '<span class="run-badge err">실패</span>',
    refused: '<span class="run-badge warn">거부됨</span>',
  }[run.status] || '';

  const counts = `
    <div class="run-counts">
      <span>새로 적재 <b>${c.ingested ?? 0}</b></span>
      <span>변경 없음 <b>${c.idempotent ?? 0}</b></span>
      <span>건너뜀 <b>${c.skipped ?? 0}</b></span>
      ${run.reconcile && !run.dry_run
        ? `<span>내림 <b>${c.pruned ?? 0}</b></span><span>되살림 <b>${c.revived ?? 0}</b></span>`
        : ''}
    </div>`;

  const plan = run.plan || {};
  const pruneList = (plan.prune || []);
  let preview = '';
  if (run.dry_run && run.status === 'succeeded') {
    preview = pruneList.length
      ? `<div class="run-preview">
           <div class="run-preview-head">Notion 에서 사라진 문서 ${pruneList.length}건 — 검색에서 내립니다</div>
           <ul>${pruneList.map((d) => `<li>${esc(d.title || d.rid)}</li>`).join('')}</ul>
           <button id="src-confirm" class="btn-danger">확인하고 적용</button>
         </div>`
      : '<div class="run-preview">사라진 문서가 없습니다.</div>';
  }

  const reason = run.reason ? `<div class="run-reason">${esc(run.reason)}</div>` : '';

  el.innerHTML = `<div class="run-card">
      <div class="run-head">${badge}<span class="run-id">${esc(run.run_id.slice(0, 8))}</span></div>
      ${counts}${reason}${preview}
    </div>`;

  const btn = document.getElementById('src-confirm');
  if (btn) btn.addEventListener('click', () => confirmPlan(run.run_id));
}

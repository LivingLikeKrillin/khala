/**
 * 그래프 뷰 — vis-network 기반 엔티티 관계 그래프.
 * 엔티티 = Nexus가 인덱싱한 서비스·컴포넌트·개념. 검색 입력은 자동완성으로
 * 실제 인덱싱된 엔티티를 제안한다. 빈 화면엔 무엇을 입력할지 안내한다.
 */

import { getGraph, suggestEntities } from '../api.js';
import { showToast } from '../components/toast.js';

let network = null;
let nodesDS = null;
let edgesDS = null;
let loadedEntities = new Set();
let acTimer = null;

export function render(container) {
  container.innerHTML = `
    <div class="graph-layout">
      <div class="graph-container">
        <div class="graph-toolbar">
          <div class="graph-search-wrap">
            <input type="text" class="graph-search" id="graph-search" autocomplete="off"
              placeholder="서비스·컴포넌트 검색 (예: payment-service)">
            <div class="graph-autocomplete hidden" id="graph-autocomplete"></div>
          </div>
          <span class="graph-hint">엔티티 = 인덱싱된 서비스·컴포넌트·개념</span>
        </div>
        <div class="graph-canvas" id="graph-canvas">
          <div class="graph-empty" id="graph-empty">
            <div class="graph-empty-title">엔티티 관계를 탐색하세요</div>
            <p class="graph-empty-text">
              서비스나 컴포넌트 이름을 입력하면 그 주변의 <strong>설계 관계</strong>와
              <strong>관측 관계</strong>를 그래프로 펼칩니다. 입력하면 인덱싱된 이름이 자동완성됩니다.
            </p>
          </div>
        </div>
        <div class="graph-legend">
          <div class="graph-legend-item"><div class="legend-line designed"></div><span>설계 관계 (Designed)</span></div>
          <div class="graph-legend-item"><div class="legend-line observed"></div><span>관측 관계 (Observed)</span></div>
          <div class="graph-legend-item"><div class="legend-line conflict"></div><span>불일치 (Conflict)</span></div>
        </div>
      </div>
      <div class="graph-detail-panel hidden" id="graph-detail-panel">
        <h3 id="detail-title"></h3>
        <div id="detail-content"></div>
      </div>
    </div>
  `;

  initNetwork();
  bindEvents();

  const match = window.location.hash.match(/#\/graph\/(.+)/);
  if (match) {
    const entity = decodeURIComponent(match[1]);
    document.getElementById('graph-search').value = entity;
    loadEntity(entity);
  }
  updateEmptyState();
}

function initNetwork() {
  nodesDS = new vis.DataSet();
  edgesDS = new vis.DataSet();

  const canvas = document.getElementById('graph-canvas');
  network = new vis.Network(canvas, { nodes: nodesDS, edges: edgesDS }, {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: { gravitationalConstant: -260, springLength: 260, springConstant: 0.04, avoidOverlap: 1 },
      stabilization: { iterations: 180 },
    },
    nodes: {
      shape: 'dot',
      size: 18,
      color: { background: '#161b23', border: '#3a434f', highlight: { background: '#1c2531', border: '#6fb0e6' } },
      borderWidth: 1.5,
      font: { color: '#e9ecf1', size: 13, face: 'Pretendard, sans-serif', strokeWidth: 4, strokeColor: '#0a0c10' },
    },
    edges: {
      smooth: { type: 'curvedCW', roundness: 0.15 },
      color: { color: '#5b93c4', highlight: '#6fb0e6' },
      width: 1,
      font: { color: '#aab2bf', size: 11, face: 'Pretendard, sans-serif', strokeWidth: 0, background: 'rgba(13,17,23,0.85)', vadjust: -1 },
      labelHighlightBold: false,
    },
    interaction: { hover: true, tooltipDelay: 200 },
  });

  network.on('stabilizationIterationsDone', () => {
    network.setOptions({ physics: false });
    network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
  });

  network.on('click', async (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const node = nodesDS.get(nodeId);
      if (node && node.entityRid) {
        showDetail(node);
        if (!loadedEntities.has(nodeId)) await loadEntity(nodeId, 1);
      }
    } else if (params.edges.length > 0) {
      const edge = edgesDS.get(params.edges[0]);
      if (edge) showEdgeDetail(edge);
    } else {
      hideDetail();
    }
  });
}

function bindEvents() {
  const searchInput = document.getElementById('graph-search');

  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      hideAutocomplete();
      const val = searchInput.value.trim();
      if (val) startEntity(val);
    } else if (e.key === 'Escape') {
      hideAutocomplete();
    }
  });

  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    clearTimeout(acTimer);
    if (q.length < 1) { hideAutocomplete(); return; }
    acTimer = setTimeout(() => loadAutocomplete(q), 200);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.graph-search-wrap')) hideAutocomplete();
  });
}

async function loadAutocomplete(q) {
  try {
    const { data } = await suggestEntities(q, { limit: 8 });
    const items = (data || []).map((it) => (typeof it === 'string' ? { name: it } : it)).filter((it) => it && it.name);
    const box = document.getElementById('graph-autocomplete');
    if (!items.length) { hideAutocomplete(); return; }
    box.innerHTML = items
      .map((it) => `<button type="button" class="graph-ac-item" data-name="${escapeAttr(it.name)}">
        <span class="graph-ac-name">${escapeHtml(it.name)}</span>${it.type ? `<span class="graph-ac-type">${escapeHtml(it.type)}</span>` : ''}
      </button>`)
      .join('');
    box.querySelectorAll('.graph-ac-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('graph-search').value = btn.dataset.name;
        hideAutocomplete();
        startEntity(btn.dataset.name);
      });
    });
    box.classList.remove('hidden');
  } catch {
    hideAutocomplete();
  }
}

function hideAutocomplete() {
  const box = document.getElementById('graph-autocomplete');
  if (box) { box.classList.add('hidden'); box.innerHTML = ''; }
}

function startEntity(name) {
  nodesDS.clear();
  edgesDS.clear();
  loadedEntities.clear();
  loadEntity(name, 2);
}

async function loadEntity(entityName, hops = 2) {
  try {
    if (network) network.setOptions({ physics: true });
    const { data, meta } = await getGraph(entityName, { hops, include_evidence: true });

    if (meta && meta.no_relations) {
      showToast('이 엔티티는 인덱싱돼 있으나 아직 관계 데이터가 없어 노드만 표시합니다', 'info');
    }

    const center = data.center_entity;
    const centerId = center.name;
    if (!nodesDS.get(centerId)) {
      nodesDS.add({
        id: centerId,
        label: center.name,
        color: { background: '#12161d', border: '#6fb0e6' },
        size: 26,
        font: { color: '#ffffff', size: 14, strokeWidth: 4, strokeColor: '#0a0c10' },
        entityRid: center.rid,
        entityType: center.type || 'Service',
        entityDesc: center.description || '',
        entityAliases: center.aliases || [],
      });
    }
    loadedEntities.add(centerId);

    for (const e of (data.edges || [])) {
      addEntityNode(e.from_name, e.from_rid);
      addEntityNode(e.to_name, e.to_rid);
      const edgeId = `d-${e.rid}`;
      if (!edgesDS.get(edgeId)) {
        edgesDS.add({
          id: edgeId, from: e.from_name, to: e.to_name, label: e.edge_type, arrows: 'to',
          color: { color: '#5b93c4', highlight: '#6fb0e6' },
          width: Math.max(1, (e.confidence || 0.5) * 2.5), dashes: false, edgeData: e,
        });
      }
    }

    for (const o of (data.observed_edges || [])) {
      addEntityNode(o.from_name);
      addEntityNode(o.to_name);
      const edgeId = `o-${o.rid}`;
      if (!edgesDS.get(edgeId)) {
        const color = (o.error_rate || 0) > 0.05 ? '#e0736f' : '#eaa44e';
        edgesDS.add({
          id: edgeId, from: o.from_name, to: o.to_name,
          label: `${o.edge_type}\n(${o.call_count || 0} calls)`, arrows: 'to', dashes: [8, 4],
          color: { color }, width: Math.max(1, Math.min(4, Math.log10((o.call_count || 1) + 1) * 2)), edgeData: o,
        });
      }
    }
    updateEmptyState();
  } catch (err) {
    if (err.status === 404) {
      showToast('이 엔티티에는 관계 데이터가 없습니다 (관계 미추출·관측 미집계, 또는 이름 불일치)', 'warning');
    } else {
      showToast(err.message, 'error');
    }
  }
}

function addEntityNode(name, rid = null) {
  if (!name || nodesDS.get(name)) return;
  nodesDS.add({ id: name, label: name, entityRid: rid || '', entityType: '', entityDesc: '', entityAliases: [] });
}

function updateEmptyState() {
  const empty = document.getElementById('graph-empty');
  if (!empty) return;
  empty.style.display = (nodesDS && nodesDS.length > 0) ? 'none' : '';
}

function showDetail(node) {
  const panel = document.getElementById('graph-detail-panel');
  panel.classList.remove('hidden');
  document.getElementById('detail-title').textContent = node.label;
  document.getElementById('detail-content').innerHTML = `
    <div class="graph-detail-section">
      <h4>정보</h4>
      <p>타입: ${escapeHtml(node.entityType || '알 수 없음')}</p>
      ${node.entityDesc ? `<p>${escapeHtml(node.entityDesc)}</p>` : ''}
      ${(node.entityAliases || []).length > 0 ? `<p>별칭: ${escapeHtml(node.entityAliases.join(', '))}</p>` : ''}
    </div>
    <div class="graph-detail-section">
      <h4>연결</h4>
      <p>이 노드를 클릭하면 관계를 확장합니다.</p>
    </div>
  `;
}

function showEdgeDetail(edge) {
  const panel = document.getElementById('graph-detail-panel');
  panel.classList.remove('hidden');
  const d = edge.edgeData || {};
  document.getElementById('detail-title').textContent = `${edge.from} → ${edge.to}`;
  let html = `<div class="graph-detail-section"><h4>${escapeHtml(d.edge_type || '')}</h4>`;
  if (d.confidence !== undefined) html += `<p>신뢰도: ${(d.confidence * 100).toFixed(0)}%</p>`;
  if (d.call_count !== undefined) {
    html += `<p>호출 수: ${d.call_count}</p>`;
    html += `<p>에러율: ${((d.error_rate || 0) * 100).toFixed(1)}%</p>`;
    if (d.latency_p95) html += `<p>P95 지연: ${d.latency_p95}ms</p>`;
  }
  if (d.evidence && d.evidence.length > 0) {
    html += `</div><div class="graph-detail-section"><h4>근거</h4><ul>`;
    for (const ev of d.evidence) {
      html += `<li><strong>${escapeHtml(ev.doc_title || '')}</strong> (${escapeHtml(ev.section_path || '')})<br><small>${escapeHtml(ev.text || '')}</small></li>`;
    }
    html += `</ul>`;
  }
  if (d.sample_trace_ids && d.sample_trace_ids.length > 0) {
    html += `</div><div class="graph-detail-section"><h4>Trace</h4>`;
    html += `<p>trace_query_ref: ${escapeHtml(d.trace_query_ref || '')}</p>`;
    html += `<p>샘플: ${escapeHtml(d.sample_trace_ids.slice(0, 3).join(', '))}</p>`;
  }
  html += `</div>`;
  document.getElementById('detail-content').innerHTML = html;
}

function hideDetail() {
  document.getElementById('graph-detail-panel').classList.add('hidden');
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
function escapeAttr(str) {
  return String(str).replace(/"/g, '&quot;');
}

export function destroy() {
  clearTimeout(acTimer);
  if (network) { network.destroy(); network = null; }
  nodesDS = null;
  edgesDS = null;
  loadedEntities.clear();
}

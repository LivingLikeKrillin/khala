/**
 * 그래프 뷰.
 * vis-network 기반 엔티티 관계 그래프.
 */

import { getGraph, suggestEntities } from '../api.js';
import { showToast } from '../components/toast.js';

let network = null;
let nodesDS = null;
let edgesDS = null;
let loadedEntities = new Set();

export function render(container) {
  container.innerHTML = `
    <div class="graph-layout">
      <div class="graph-container">
        <div class="graph-toolbar">
          <input type="text" class="graph-search" id="graph-search"
            placeholder="엔티티 이름 검색... (Enter로 조회)">
        </div>
        <div class="graph-canvas" id="graph-canvas"></div>
        <div class="graph-legend">
          <div class="graph-legend-item">
            <div class="legend-line designed"></div>
            <span>설계 관계 (Designed)</span>
          </div>
          <div class="graph-legend-item">
            <div class="legend-line observed"></div>
            <span>관측 관계 (Observed)</span>
          </div>
          <div class="graph-legend-item">
            <div class="legend-line conflict"></div>
            <span>불일치 (Conflict)</span>
          </div>
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

  // URL에서 엔티티 파라미터 확인
  const hash = window.location.hash;
  const match = hash.match(/#\/graph\/(.+)/);
  if (match) {
    const entity = decodeURIComponent(match[1]);
    document.getElementById('graph-search').value = entity;
    loadEntity(entity);
  }
}

function initNetwork() {
  nodesDS = new vis.DataSet();
  edgesDS = new vis.DataSet();

  const canvas = document.getElementById('graph-canvas');
  network = new vis.Network(canvas, { nodes: nodesDS, edges: edgesDS }, {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: { gravitationalConstant: -80, springLength: 150 },
      stabilization: { iterations: 100 },
    },
    nodes: {
      shape: 'dot',
      size: 20,
      color: { background: '#242736', border: '#6c8cff', highlight: { background: '#6c8cff', border: '#8aa4ff' } },
      borderWidth: 2,
      font: { color: '#e4e6eb', size: 13, face: 'Pretendard, sans-serif' },
    },
    edges: {
      smooth: { type: 'curvedCW', roundness: 0.15 },
      font: { color: '#6b7280', size: 11, face: 'Pretendard, sans-serif', strokeWidth: 0 },
    },
    interaction: { hover: true, tooltipDelay: 200 },
  });

  // 노드 클릭: 확장
  network.on('click', async (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const node = nodesDS.get(nodeId);
      if (node && node.entityRid) {
        showDetail(node);
        if (!loadedEntities.has(nodeId)) {
          await loadEntity(nodeId, 1);
        }
      }
    } else if (params.edges.length > 0) {
      const edgeId = params.edges[0];
      const edge = edgesDS.get(edgeId);
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
      const val = searchInput.value.trim();
      if (val) {
        // 기존 그래프 초기화
        nodesDS.clear();
        edgesDS.clear();
        loadedEntities.clear();
        loadEntity(val, 2);
      }
    }
  });
}

async function loadEntity(entityName, hops = 2) {
  try {
    const { data } = await getGraph(entityName, { hops, include_evidence: true });

    const center = data.center_entity;
    const centerId = center.name;

    // center 노드 추가
    if (!nodesDS.get(centerId)) {
      nodesDS.add({
        id: centerId,
        label: center.name,
        color: { background: '#6c8cff', border: '#8aa4ff' },
        size: 28,
        font: { color: '#fff', size: 14 },
        entityRid: center.rid,
        entityType: center.type || 'Service',
        entityDesc: center.description || '',
        entityAliases: center.aliases || [],
      });
    }
    loadedEntities.add(centerId);

    // designed edges
    for (const e of (data.edges || [])) {
      addEntityNode(e.from_name, e.from_rid);
      addEntityNode(e.to_name, e.to_rid);

      const edgeId = `d-${e.rid}`;
      if (!edgesDS.get(edgeId)) {
        edgesDS.add({
          id: edgeId,
          from: e.from_name,
          to: e.to_name,
          label: e.edge_type,
          arrows: 'to',
          color: { color: '#60a5fa', highlight: '#93bbff' },
          width: Math.max(1, (e.confidence || 0.5) * 3),
          dashes: false,
          edgeData: e,
        });
      }
    }

    // observed edges
    for (const o of (data.observed_edges || [])) {
      addEntityNode(o.from_name);
      addEntityNode(o.to_name);

      const edgeId = `o-${o.rid}`;
      if (!edgesDS.get(edgeId)) {
        const color = (o.error_rate || 0) > 0.05 ? '#f87171' : '#fb923c';
        edgesDS.add({
          id: edgeId,
          from: o.from_name,
          to: o.to_name,
          label: `${o.edge_type}\n(${o.call_count || 0} calls)`,
          arrows: 'to',
          dashes: [8, 4],
          color: { color },
          width: Math.max(1, Math.min(4, Math.log10((o.call_count || 1) + 1) * 2)),
          edgeData: o,
        });
      }
    }

    network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
  } catch (err) {
    if (err.status === 404) {
      showToast('엔티티를 찾을 수 없습니다', 'warning');
    } else {
      showToast(err.message, 'error');
    }
  }
}

function addEntityNode(name, rid = null) {
  if (!name || nodesDS.get(name)) return;
  nodesDS.add({
    id: name,
    label: name,
    entityRid: rid || '',
    entityType: '',
    entityDesc: '',
    entityAliases: [],
  });
}

function showDetail(node) {
  const panel = document.getElementById('graph-detail-panel');
  panel.classList.remove('hidden');

  document.getElementById('detail-title').textContent = node.label;
  document.getElementById('detail-content').innerHTML = `
    <div class="graph-detail-section">
      <h4>정보</h4>
      <p>타입: ${node.entityType || '알 수 없음'}</p>
      ${node.entityDesc ? `<p>${node.entityDesc}</p>` : ''}
      ${(node.entityAliases || []).length > 0 ? `<p>별칭: ${node.entityAliases.join(', ')}</p>` : ''}
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

  let html = `<div class="graph-detail-section"><h4>${d.edge_type || ''}</h4>`;

  if (d.confidence !== undefined) {
    html += `<p>신뢰도: ${(d.confidence * 100).toFixed(0)}%</p>`;
  }
  if (d.call_count !== undefined) {
    html += `<p>호출 수: ${d.call_count}</p>`;
    html += `<p>에러율: ${((d.error_rate || 0) * 100).toFixed(1)}%</p>`;
    if (d.latency_p95) html += `<p>P95 지연: ${d.latency_p95}ms</p>`;
  }

  // evidence
  if (d.evidence && d.evidence.length > 0) {
    html += `</div><div class="graph-detail-section"><h4>근거</h4><ul>`;
    for (const ev of d.evidence) {
      html += `<li><strong>${ev.doc_title || ''}</strong> (${ev.section_path || ''})<br><small>${ev.text || ''}</small></li>`;
    }
    html += `</ul>`;
  }

  // trace links
  if (d.sample_trace_ids && d.sample_trace_ids.length > 0) {
    html += `</div><div class="graph-detail-section"><h4>Trace</h4>`;
    html += `<p>trace_query_ref: ${d.trace_query_ref || ''}</p>`;
    html += `<p>샘플: ${d.sample_trace_ids.slice(0, 3).join(', ')}</p>`;
  }

  html += `</div>`;
  document.getElementById('detail-content').innerHTML = html;
}

function hideDetail() {
  document.getElementById('graph-detail-panel').classList.add('hidden');
}

export function destroy() {
  if (network) {
    network.destroy();
    network = null;
  }
  nodesDS = null;
  edgesDS = null;
  loadedEntities.clear();
}

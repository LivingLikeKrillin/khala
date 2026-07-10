/**
 * 상태바 컴포넌트. 30초마다 /status를 폴링.
 */

import { getStatus } from '../api.js';
import { freshnessLabel } from '../freshness.js';

let intervalId = null;

export function initStatusBar() {
  update();
  intervalId = setInterval(update, 30000);
}

export function stopStatusBar() {
  if (intervalId) clearInterval(intervalId);
}

async function update() {
  try {
    const { data } = await getStatus();

    setDot('dot-db', data.db_connected);
    setDot('dot-ollama', data.ollama_connected);
    setDot('dot-tempo', data.tempo_connected);

    // 익명(permissive) 모드면 PUBLIC-only 배너 노출 — 빈/부분 결과가 버그가 아닌 보안 경계임을 알림
    const banner = document.getElementById('auth-banner');
    if (banner) banner.classList.toggle('hidden', !data.anonymous);

    const statusText = document.getElementById('status-text');
    if (data.db_connected) {
      statusText.textContent = '';
    } else {
      statusText.textContent = 'DB 연결 끊김';
      statusText.style.color = 'var(--danger)';
    }

    const badgeDocs = document.getElementById('badge-docs');
    badgeDocs.textContent = `${data.documents_count ?? 0} 문서`;

    // 코퍼스 신선도 — 적재 이력이 있을 때만. 지난주 코퍼스가 조용히 줄었을 때 화면이
    // 아무 말도 안 했던 그 침묵을 메운다.
    const badgeFresh = document.getElementById('badge-freshness');
    if (badgeFresh) {
      const label = freshnessLabel(data.last_ingest_at);
      badgeFresh.textContent = label;
      badgeFresh.classList.toggle('hidden', !label);
    }

    const badgeDiff = document.getElementById('badge-diff');
    const diff = data.diff_summary;
    if (diff) {
      const total = (diff.doc_only_count || 0) + (diff.observed_only_count || 0) + (diff.conflict_count || 0);
      badgeDiff.textContent = `${total} 불일치`;
      if (total > 0) {
        badgeDiff.classList.add('has-issues');
      } else {
        badgeDiff.classList.remove('has-issues');
      }
    }
  } catch {
    document.getElementById('status-text').textContent = '서버 연결 실패';
    document.getElementById('status-text').style.color = 'var(--danger)';
    setDot('dot-db', false);
    setDot('dot-ollama', false);
    setDot('dot-tempo', false);
  }
}

function setDot(id, ok) {
  const dot = document.getElementById(id);
  dot.classList.toggle('ok', !!ok);
  dot.classList.toggle('fail', !ok);
}

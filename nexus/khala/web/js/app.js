/**
 * Khala SPA 라우터 + 초기화.
 */

import { initStatusBar } from './components/status-bar.js';
import * as chatView from './views/chat.js';
import * as graphView from './views/graph.js';
import * as documentsView from './views/documents.js';
import * as diffView from './views/diff.js';
import * as uploadView from './views/upload.js';

const views = {
  chat: chatView,
  graph: graphView,
  documents: documentsView,
  diff: diffView,
  upload: uploadView,
};

let currentView = null;

function getViewName(hash) {
  const match = (hash || '#/chat').match(/#\/(\w+)/);
  return match ? match[1] : 'chat';
}

function navigate(viewName) {
  // 이전 뷰 정리
  if (currentView && views[currentView]?.destroy) {
    views[currentView].destroy();
  }

  // 네비게이션 active 상태
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === viewName);
  });

  // 뷰 렌더링
  const container = document.getElementById('main-content');
  const view = views[viewName];
  if (view) {
    currentView = viewName;
    view.render(container);
  } else {
    container.innerHTML = `<div class="chat-empty"><div class="chat-empty-title">404</div></div>`;
  }
}

// Diff 배지 클릭 → diff 뷰로 이동
document.getElementById('badge-diff').addEventListener('click', () => {
  window.location.hash = '#/diff';
});

// 해시 라우팅
window.addEventListener('hashchange', () => {
  navigate(getViewName(window.location.hash));
});

// 초기화
initStatusBar();
navigate(getViewName(window.location.hash));

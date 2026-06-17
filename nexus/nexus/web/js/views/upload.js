/**
 * 파일 업로드 뷰.
 */

import { uploadFile } from '../api.js';
import { showToast } from '../components/toast.js';

export function render(container) {
  container.innerHTML = `
    <div class="upload-layout">
      <div class="upload-zone" id="upload-zone">
        <div class="upload-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="42" height="42" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 14.9A6 6 0 1 1 15.7 8.5h1.3a4.5 4.5 0 0 1 1.6 8.7"/><path d="M12 12v8"/><path d="m8.5 15 3.5-3.5L15.5 15"/>
          </svg>
        </div>
        <div class="upload-text">Markdown 파일을 드래그하거나 클릭하여 업로드</div>
        <div class="upload-hint">.md 파일만 지원됩니다</div>
        <input type="file" id="upload-input" accept=".md" style="display:none">
      </div>
      <div id="upload-result-area"></div>
    </div>
  `;

  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('upload-input');

  zone.addEventListener('click', () => input.click());

  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('dragover');
  });

  zone.addEventListener('dragleave', () => {
    zone.classList.remove('dragover');
  });

  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  input.addEventListener('change', () => {
    if (input.files[0]) handleFile(input.files[0]);
    input.value = '';
  });
}

async function handleFile(file) {
  if (!file.name.endsWith('.md')) {
    showToast('Markdown (.md) 파일만 업로드 가능합니다', 'warning');
    return;
  }

  const area = document.getElementById('upload-result-area');
  area.innerHTML = `<div class="upload-result" style="color:var(--text-muted)">업로드 중: ${escapeHtml(file.name)}...</div>`;

  try {
    const { data } = await uploadFile(file);

    let cls = 'success';
    let msg = data.message || '업로드 완료';
    if (data.quarantined) {
      cls = 'warning';
      msg = `PII 감지로 격리되었습니다: ${file.name}`;
    }

    area.innerHTML = `
      <div class="upload-result ${cls}">
        <strong>${msg}</strong>
        <div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">
          <div>문서 RID: ${data.doc_rid || '-'}</div>
          <div>경로: ${data.source_uri || '-'}</div>
        </div>
      </div>
    `;

    showToast(msg, cls === 'warning' ? 'warning' : 'success');
  } catch (err) {
    let msg = err.message;
    if (err.status === 409) {
      msg = `파일이 이미 존재합니다: ${file.name}`;
    }

    area.innerHTML = `<div class="upload-result error"><strong>${escapeHtml(msg)}</strong></div>`;
    showToast(msg, 'error');
  }
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

export function destroy() {}

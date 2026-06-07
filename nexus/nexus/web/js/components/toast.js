/**
 * Toast 알림 컴포넌트.
 */

const container = document.getElementById('toast-container');

export function showToast(message, type = 'error', duration = 4000) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);

  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateX(100%)';
    el.style.transition = 'all 0.3s';
    setTimeout(() => el.remove(), 300);
  }, duration);
}

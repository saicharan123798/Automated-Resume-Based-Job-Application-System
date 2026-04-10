/**
 * AutoJob – main.js
 * Shared utilities and UI polish across all pages.
 */

// ─── Auto-dismiss flash messages ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const flashes = document.querySelectorAll('#flash-container > div');
  flashes.forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.5s ease, max-height 0.5s ease';
      el.style.opacity = '0';
      el.style.maxHeight = '0';
      el.style.overflow = 'hidden';
      setTimeout(() => el.remove(), 500);
    }, 5000);
  });
});

// ─── Sidebar active link (fallback for dynamic pages) ────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const path = window.location.pathname;
  document.querySelectorAll('.sidebar-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href && path.startsWith(href) && href !== '/') {
      link.classList.add('active');
    }
  });
});

// ─── Global helper: confirmAction ────────────────────────────────────────────
function confirmAction(msg, onConfirm) {
  if (window.confirm(msg)) onConfirm();
}

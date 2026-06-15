// Demo-mode highlight ring around the target element (BLUEPRINT §5).
// window.__tg.highlight(box) draws a pulsing ring; window.__tg.reset() clears it
// (reset is chained so cursor/highlight/zoom all clean up on one call).
(() => {
  let ring = null;
  window.__tg = window.__tg || {};

  window.__tg.highlight = (b) => {
    if (ring) ring.remove();
    ring = document.createElement('div');
    ring.id = '__tg_highlight';
    ring.style.cssText = `position:fixed;z-index:2147483646;pointer-events:none;
      left:${b.x - 6}px;top:${b.y - 6}px;width:${b.width + 12}px;height:${b.height + 12}px;
      border:3px solid #ff5a36;border-radius:8px;
      box-shadow:0 0 0 4px rgba(255,90,54,.25);
      animation:tgpulse 1s ease-in-out infinite;`;
    (document.body || document.documentElement).appendChild(ring);
    if (!document.getElementById('__tg_kf')) {
      const s = document.createElement('style');
      s.id = '__tg_kf';
      s.textContent = '@keyframes tgpulse{50%{box-shadow:0 0 0 10px rgba(255,90,54,0)}}';
      document.head.appendChild(s);
    }
  };

  const prev = window.__tg.reset || (() => {});
  window.__tg.reset = () => { prev(); if (ring) { ring.remove(); ring = null; } };
})();

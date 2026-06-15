// Demo-mode zoom (BLUEPRINT §5): a CSS transform on <html> with the origin at the
// element centre — cheaper and more accurate than FFmpeg zoompan, and frame-accurate
// in capture. window.__tg.zoom(box, scale); window.__tg.reset() restores scale 1.
(() => {
  // Read documentElement lazily — at init-script time (document_start) it doesn't exist yet.
  window.__tg = window.__tg || {};

  window.__tg.zoom = (b, scale = 1.4) => {
    const root = document.documentElement;
    root.style.transition = 'transform .5s ease';
    root.style.transformOrigin = `${b.x + b.width / 2}px ${b.y + b.height / 2}px`;
    root.style.transform = `scale(${scale})`;
  };

  const prev = window.__tg.reset || (() => {});
  window.__tg.reset = () => { prev(); document.documentElement.style.transform = 'scale(1)'; };
})();

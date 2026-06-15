// Demo-mode cursor — an injected DOM node so it appears in any capture and is
// frame-accurate (BLUEPRINT §5). window.__tg.cursorTo({x,y,width,height}) glides it
// to the centre of an element's bounding box.
(() => {
  const c = document.createElement('div');
  c.id = '__tg_cursor';
  c.style.cssText = `position:fixed;width:22px;height:22px;z-index:2147483647;
    pointer-events:none;left:50%;top:50%;
    transition:left .8s cubic-bezier(.4,0,.2,1),top .8s cubic-bezier(.4,0,.2,1);
    background:no-repeat center/contain url("data:image/svg+xml;utf8,` +
    encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' +
      '<path d="M3 2l7 18 2.5-7.5L20 10z" fill="black" stroke="white" stroke-width="1.5"/></svg>') +
    `");`;
  const mount = () => (document.body || document.documentElement).appendChild(c);
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  window.__tg = window.__tg || {};
  window.__tg.cursorTo = (b) => {
    c.style.left = (b.x + b.width / 2) + 'px';
    c.style.top = (b.y + b.height / 2) + 'px';
  };
})();

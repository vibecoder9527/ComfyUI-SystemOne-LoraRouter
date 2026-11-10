// Row context menus for LoRA Library and Theme tables.
//
// Vue Nodes 2.0 (frontend 1.57.6): LGraphNode.vue binds
// `@contextmenu="handleContextMenu"` on the node root (bubble, not capture).
// That handler calls preventDefault, stopPropagation, handleNodeRightClick,
// then showNodeOptions(...) to open the native node menu. A row handler that
// only preventDefault still bubbles, so both menus appear. Stopping the
// contextmenu event on the row (capture + stopPropagation /
// stopImmediatePropagation) keeps the native menu from opening there.
// Right-click elsewhere on the node is not stopped, so the native menu stays.
//
// pointerdown/mousedown with button===2 are also stopped from bubbling
// (without preventDefault, which can cancel the following contextmenu).
// Left-click (button 0) is not touched, so drag/select keep working.
//
// Legacy canvas: LiteGraph opens the node menu from the canvas
// processContextMenu path. DOM row handlers already stop the event when the
// click hits a row. As a fallback, hit-test registered row elements and skip
// processContextMenu / getExtraMenuOptions only for those hits.

export function isRightClickEvent(event) {
  if (!event) return false;
  if (event.type === "contextmenu") return true;
  return event.button === 2;
}

export function stopRowContextMenuEvent(event, { preventDefault = true } = {}) {
  if (!event) return false;
  if (preventDefault) event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

export function eventHitsElement(event, el) {
  if (!event || !el || typeof el.getBoundingClientRect !== "function") return false;
  const x = Number(event.clientX);
  const y = Number(event.clientY);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
  const box = el.getBoundingClientRect();
  return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
}

export function hitTestNodeRows(node, event) {
  const rows = node?.__s1RowMenuEls;
  if (!Array.isArray(rows) || !event) return false;
  return rows.some((el) => eventHitsElement(event, el));
}

export function shouldSuppressNativeNodeMenu(node, event) {
  return hitTestNodeRows(node, event);
}

export function bindRowContextMenu(el, onMenu) {
  if (!el) return () => {};
  const onContextMenu = (event) => {
    stopRowContextMenuEvent(event, { preventDefault: true });
    if (typeof onMenu === "function") onMenu(event);
  };
  const onRightPointer = (event) => {
    if (!isRightClickEvent(event)) return;
    // Do not preventDefault: that can swallow the contextmenu event.
    stopRowContextMenuEvent(event, { preventDefault: false });
  };
  el.addEventListener("contextmenu", onContextMenu, true);
  el.addEventListener("pointerdown", onRightPointer, true);
  el.addEventListener("mousedown", onRightPointer, true);
  return () => {
    el.removeEventListener("contextmenu", onContextMenu, true);
    el.removeEventListener("pointerdown", onRightPointer, true);
    el.removeEventListener("mousedown", onRightPointer, true);
  };
}

export function registerRowMenuElement(node, el) {
  if (!node || !el) return;
  if (!Array.isArray(node.__s1RowMenuEls)) node.__s1RowMenuEls = [];
  node.__s1RowMenuEls.push(el);
}

export function clearRowMenuElements(node) {
  if (node) node.__s1RowMenuEls = [];
}

export function installNativeNodeMenuSuppress(node) {
  if (!node || node.__s1RowMenuSuppress) return node;
  node.__s1RowMenuSuppress = true;
  const previousExtra = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function s1RowMenuExtra(canvas, options, event, ...rest) {
    const ev = event || canvas?.last_event || canvas?.current_event;
    if (shouldSuppressNativeNodeMenu(this, ev)) return [];
    return typeof previousExtra === "function"
      ? previousExtra.call(this, canvas, options, event, ...rest)
      : options;
  };
  hookCanvasProcessContextMenu();
  return node;
}

function hookCanvasProcessContextMenu() {
  const Canvas = (typeof globalThis !== "undefined" && (globalThis.LGraphCanvas || globalThis.LiteGraph?.LGraphCanvas)) || null;
  const proto = Canvas?.prototype;
  if (!proto || typeof proto.processContextMenu !== "function" || proto.__s1RowMenuHook) return;
  const previous = proto.processContextMenu;
  proto.processContextMenu = function s1RowMenuProcessContextMenu(node, event, ...rest) {
    if (node && shouldSuppressNativeNodeMenu(node, event)) return;
    return previous.call(this, node, event, ...rest);
  };
  proto.__s1RowMenuHook = true;
}

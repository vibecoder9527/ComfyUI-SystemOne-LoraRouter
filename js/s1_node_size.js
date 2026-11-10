// Auto-size policy for on-node LoRA Library / Theme editors.
//
// Width: never auto-shrink, and never override a user's manually enlarged
// width. The next width is max(current, minWidth, userMinWidth).
//
// Height: follow content so wrapped tag chips can grow the field, the row,
// and the node together, and shrink back when chips are removed. A user's
// manually set height is a floor (userMinHeight): we never shrink below
// that floor even if content gets shorter, but we still grow when content
// needs more than the user-set height. userMinHeight is recorded from
// onResize when the change is not an automatic applyEditorNodeSize, so
// auto-grown height is not treated as a user minimum.

export function nextEditorNodeSize({
  currentWidth = 0,
  currentHeight = 0,
  minWidth = 0,
  minHeight = 0,
  contentHeight = 0,
  userMinWidth = 0,
  userMinHeight = 0,
} = {}) {
  const width = Math.max(Number(currentWidth) || 0, Number(minWidth) || 0, Number(userMinWidth) || 0);
  const height = Math.max(Number(contentHeight) || 0, Number(minHeight) || 0, Number(userMinHeight) || 0);
  return { width, height };
}

export function measureHostHeight(host, fallback = 0) {
  if (!host) return Number(fallback) || 0;
  const rectHeight = typeof host.getBoundingClientRect === "function" ? host.getBoundingClientRect().height : 0;
  const raw = Math.max(Number(host.scrollHeight) || 0, Number(host.offsetHeight) || 0, Number(rectHeight) || 0);
  const floor = Number(fallback) || 0;
  return raw > 0 ? Math.max(raw, floor) : floor;
}

export function applyEditorNodeSize(node, spec = {}) {
  if (!node || !Array.isArray(node.size)) return null;
  const next = nextEditorNodeSize({
    currentWidth: node.size[0],
    currentHeight: node.size[1],
    minWidth: spec.minWidth,
    minHeight: spec.minHeight,
    contentHeight: spec.contentHeight,
    userMinWidth: node.__s1UserMinWidth || 0,
    userMinHeight: node.__s1UserMinHeight || 0,
  });
  if (node.size[0] === next.width && node.size[1] === next.height) return next;
  node.__s1AutoSizing = true;
  node.size[0] = next.width;
  node.size[1] = next.height;
  node.__s1LastAutoWidth = next.width;
  node.__s1LastAutoHeight = next.height;
  try {
    node.setSize?.(node.size);
  } finally {
    node.__s1AutoSizing = false;
  }
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
  return next;
}

export function installEditorSizeGuard(node) {
  if (!node || node.__s1SizeGuard) return node;
  node.__s1SizeGuard = true;
  const previous = node.onResize;
  node.onResize = function s1EditorOnResize(size, ...rest) {
    const next = Array.isArray(size) ? size : this.size;
    const autoWidth = this.__s1LastAutoWidth;
    const autoHeight = this.__s1LastAutoHeight;
    const fromAuto = Boolean(this.__s1AutoSizing)
      || (autoWidth != null && autoHeight != null && next?.[0] === autoWidth && next?.[1] === autoHeight);
    if (!fromAuto && Array.isArray(next)) {
      this.__s1UserMinWidth = next[0];
      this.__s1UserMinHeight = next[1];
    }
    return typeof previous === "function" ? previous.call(this, size, ...rest) : undefined;
  };
  return node;
}

export function observeEditorHostSize(host, onChange) {
  if (!host) return () => {};
  const notify = () => {
    if (typeof onChange === "function") onChange(measureHostHeight(host, 0));
  };
  if (typeof ResizeObserver !== "function") return () => {};
  const observer = new ResizeObserver(() => { notify(); });
  observer.observe(host);
  return () => observer.disconnect();
}

export function editorWidgetSizeOptions(host, minHeight) {
  const read = () => Math.max(Number(minHeight) || 0, measureHostHeight(host, minHeight));
  return { hideOnZoom: false, serialize: false, getMinHeight: read, getHeight: read };
}

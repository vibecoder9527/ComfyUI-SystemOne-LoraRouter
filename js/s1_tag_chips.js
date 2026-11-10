// Token/chip tag field for on-node Vue DOM widgets (LoRA rows and Theme table).
// Storage stays an array of strings (comma-string input is accepted and re-emitted
// as a deduped array). Legacy canvas fallback may skip this and show a comma string.

import { addTagToken, removeTagToken, tokenizeTags } from "./s1_model.js";

const CSS = `
.s1-tag-chips { display: flex; align-items: center; gap: 4px; min-width: 0; width: 100%; overflow-x: auto; overflow-y: hidden; flex-wrap: nowrap; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 2px 4px; min-height: 24px; }
.s1-tag-chips.is-locked { opacity: 0.7; pointer-events: none; }
.s1-tag-chip { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 2px; max-width: 9em; padding: 1px 4px 1px 6px; border-radius: 999px; background: rgba(61,110,168,0.55); color: inherit; font: 11px/1.3 system-ui, sans-serif; }
.s1-tag-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s1-tag-chip button { flex: 0 0 auto; width: 14px; height: 14px; border: 0; border-radius: 50%; background: transparent; color: inherit; cursor: pointer; font: 11px/14px system-ui, sans-serif; padding: 0; }
.s1-tag-chip button:hover { background: rgba(0,0,0,0.25); }
.s1-tag-chips input { flex: 1 0 4em; min-width: 4em; width: 4em; background: transparent; border: 0; color: inherit; font: inherit; padding: 2px 4px; outline: none; }
`;

let styleInjected = false;
function injectStyle() {
  if (styleInjected || typeof document === "undefined") return;
  const el = document.createElement("style");
  el.id = "s1-tag-chips-style";
  el.textContent = CSS;
  document.head.appendChild(el);
  styleInjected = true;
}

export function mountTagChips({ tags = [], suggestions = [], listId = "", onChange, locked = false } = {}) {
  injectStyle();
  let current = tokenizeTags(tags);
  const host = document.createElement("div");
  host.className = "s1-tag-chips" + (locked ? " is-locked" : "");
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = locked ? "" : "tags";
  if (listId) input.setAttribute("list", listId);
  input.disabled = Boolean(locked);
  let composing = false;

  function emit(next) {
    current = tokenizeTags(next);
    if (typeof onChange === "function") onChange(current.slice());
    paint();
  }

  function commit() {
    if (locked) return;
    const text = input.value;
    if (!String(text).trim()) {
      input.value = "";
      return;
    }
    input.value = "";
    emit(addTagToken(current, text));
  }

  function paint() {
    host.replaceChildren();
    current.forEach((tag, index) => {
      const chip = document.createElement("span");
      chip.className = "s1-tag-chip";
      const label = document.createElement("span");
      label.textContent = tag;
      label.title = tag;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.title = "Remove tag";
      if (!locked) {
        remove.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          emit(removeTagToken(current, index));
          input.focus();
        });
      }
      chip.append(label, remove);
      host.append(chip);
    });
    host.append(input);
  }

  input.addEventListener("compositionstart", () => { composing = true; });
  input.addEventListener("compositionend", () => { composing = false; });
  input.addEventListener("keydown", (event) => {
    if (locked || composing) return;
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !input.value && current.length) {
      event.preventDefault();
      emit(removeTagToken(current, current.length - 1));
    }
  });
  input.addEventListener("change", () => { commit(); });
  input.addEventListener("blur", () => { commit(); });

  if (suggestions?.length && listId) {
    // Caller owns the datalist element; we only point at its id.
  }

  paint();
  host.s1SetTags = (next) => {
    current = tokenizeTags(next);
    paint();
  };
  host.s1GetTags = () => current.slice();
  return host;
}

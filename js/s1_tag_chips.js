// Token/chip tag field for on-node Vue DOM widgets (LoRA rows and Theme table).
// Storage stays an array of strings (comma-string input is accepted and re-emitted
// as a deduped array). Weighted option tags are stored as ``age:-2`` and shown
// as ``age −2`` (Unicode minus). Legacy canvas fallback may skip this and show
// a comma string. Chips wrap onto additional lines and the field grows with
// them; there is no horizontal scrollbar. The input takes the remaining width
// on the last line.

import {
  addTagToken,
  formatTagChipLabel,
  parseTagToken,
  removeTagToken,
  tokenizeTags,
} from "./s1_model.js";

const CSS = `
.s1-tag-chips { display: flex; flex-wrap: wrap; align-items: center; align-content: flex-start; gap: 4px; min-width: 0; width: 100%; overflow: visible; height: auto; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 2px 4px; min-height: 24px; }
.s1-tag-chips.is-locked { opacity: 0.7; pointer-events: none; }
.s1-tag-chip { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 2px; max-width: 11em; padding: 1px 4px 1px 6px; border-radius: 999px; background: rgba(61,110,168,0.55); color: inherit; font: 11px/1.3 system-ui, sans-serif; border: 0; }
.s1-tag-chip.is-weighted { background: rgba(61,110,168,0.75); }
.s1-tag-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: text; }
.s1-tag-chip button { flex: 0 0 auto; width: 14px; height: 14px; border: 0; border-radius: 50%; background: transparent; color: inherit; cursor: pointer; font: 11px/14px system-ui, sans-serif; padding: 0; }
.s1-tag-chip button:hover { background: rgba(0,0,0,0.25); }
.s1-tag-chips input { flex: 1 1 4em; min-width: 4em; width: auto; background: transparent; border: 0; color: inherit; font: inherit; padding: 2px 4px; outline: none; }
.s1-tag-chip-edit { flex: 0 1 8em; min-width: 5em; width: 8em; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.2); border-radius: 999px; color: inherit; font: 11px/1.3 system-ui, sans-serif; padding: 1px 6px; outline: none; }
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

export function mountTagChips({
  tags = [],
  suggestions = [],
  listId = "",
  onChange,
  locked = false,
  plainNames = false,
} = {}) {
  injectStyle();
  const options = { plainNames: Boolean(plainNames) };
  let current = tokenizeTags(tags, options);
  let editingIndex = null;
  const host = document.createElement("div");
  host.className = "s1-tag-chips" + (locked ? " is-locked" : "");
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = locked ? "" : (options.plainNames ? "tag" : "tag or tag:weight");
  if (listId) input.setAttribute("list", listId);
  input.disabled = Boolean(locked);
  let composing = false;

  function emit(next) {
    current = tokenizeTags(next, options);
    editingIndex = null;
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
    emit(addTagToken(current, text, options));
  }

  function beginEdit(index) {
    if (locked) return;
    editingIndex = index;
    paint();
    const edit = host.querySelector(".s1-tag-chip-edit");
    if (edit) {
      edit.focus();
      edit.select();
    }
  }

  function commitEdit(index, raw) {
    const typed = String(raw ?? "").trim();
    const next = current.filter((_, itemIndex) => itemIndex !== index);
    if (typed) next.splice(index, 0, typed);
    emit(tokenizeTags(next, options));
  }

  function paint() {
    host.replaceChildren();
    current.forEach((tag, index) => {
      if (editingIndex === index && !locked) {
        const edit = document.createElement("input");
        edit.type = "text";
        edit.className = "s1-tag-chip-edit";
        edit.value = tag;
        edit.title = "Edit tag or tag:weight";
        const finish = (apply) => {
          if (editingIndex !== index) return;
          if (apply) commitEdit(index, edit.value);
          else {
            editingIndex = null;
            paint();
          }
        };
        edit.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            finish(true);
          } else if (event.key === "Escape") {
            event.preventDefault();
            finish(false);
          }
        });
        edit.addEventListener("blur", () => finish(true));
        host.append(edit);
        return;
      }
      const parsed = parseTagToken(tag);
      const chip = document.createElement("span");
      chip.className = "s1-tag-chip" + (parsed.weight != null ? " is-weighted" : "");
      const label = document.createElement("span");
      label.textContent = formatTagChipLabel(parsed);
      label.title = parsed.canonical;
      if (!locked) {
        label.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          beginEdit(index);
        });
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.title = "Remove tag";
      if (!locked) {
        remove.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          emit(removeTagToken(current, index, options));
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
      emit(removeTagToken(current, current.length - 1, options));
    }
  });
  input.addEventListener("change", () => { commit(); });
  input.addEventListener("blur", () => { commit(); });

  if (suggestions?.length && listId) {
    // Caller owns the datalist element; we only point at its id.
    // Suggestions should be plain names so autocomplete matches the name part.
  }

  paint();
  host.s1SetTags = (next) => {
    current = tokenizeTags(next, options);
    editingIndex = null;
    paint();
  };
  host.s1GetTags = () => current.slice();
  return host;
}

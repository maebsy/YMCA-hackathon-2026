"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type ChangeEvent, type KeyboardEvent, type RefObject } from "react";
import { bestCompletion, canCompleteInput, loadPublicRepos, matchingRepos, parseRepoPrefix } from "./repo-suggest";

type Completion = { typed: string; full: string; start: number };
type Menu = { typed: string; names: string[]; active: number; open: boolean; loading: boolean };
const emptyMenu: Menu = { typed: "", names: [], active: -1, open: false, loading: false };

export function useRepoAutocomplete({ value, setValue, inputRef }: {
  value: string; setValue: (value: string) => void; inputRef: RefObject<HTMLInputElement | null>;
}) {
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const [menu, setMenu] = useState<Menu>(emptyMenu);
  const completion = useRef<Completion | null>(null);
  const selection = useRef<Completion | null>(null);
  const revision = useRef(0);
  const composing = useRef(false);
  const mounted = useRef(false);
  const prefetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prefetched = useRef(new Set<string>());

  useEffect(() => {
    const lifecycle = mounted;
    const operation = revision;
    const timer = prefetchTimer;
    lifecycle.current = true;
    const doc = inputRef.current?.ownerDocument;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && target !== inputRef.current && !listRef.current?.contains(target)) {
        operation.current++;
        setMenu(current => ({ ...current, open: false }));
      }
    };
    doc?.addEventListener("pointerdown", outside);
    return () => {
      lifecycle.current = false;
      operation.current++;
      if (timer.current) clearTimeout(timer.current);
      doc?.removeEventListener("pointerdown", outside);
    };
  }, [inputRef]);

  // 같은 최종 value로 돌아오는 React 배치 갱신에도 새 선택 작업을 적용합니다.
  useLayoutEffect(() => {
    const pending = selection.current;
    selection.current = null;
    const input = inputRef.current;
    if (pending && input && !input.disabled && !input.readOnly && value === pending.full && input.value === pending.full) {
      input.setSelectionRange(pending.start, pending.full.length);
    }
  });

  useEffect(() => {
    const list = listRef.current;
    if (menu.open && list) {
      if (menu.active >= 0) list.children[menu.active]?.scrollIntoView({ block: "nearest" });
      else list.scrollTop = 0;
    }
  }, [menu.open, menu.active, menu.names]);

  function applyName(typed: string, name: string) {
    const prefix = parseRepoPrefix(typed);
    if (!prefix) return;
    const base = typed.slice(0, typed.length - prefix.partial.length);
    const starts = name.toLowerCase().startsWith(prefix.partial.toLowerCase());
    const full = starts ? typed + name.slice(prefix.partial.length) : base + name;
    const next = { typed, full, start: starts ? typed.length : base.length };
    completion.current = next;
    selection.current = next;
    setValue(full);
  }

  function request(typed: string, input: HTMLInputElement, inline: boolean) {
    const current = ++revision.current;
    const prefix = parseRepoPrefix(typed);
    if (!prefix) { setMenu(emptyMenu); return; }
    // '/' 입력 이벤트 안에서 열어 API를 기다리는 동안에도 같은 자리를 유지합니다.
    setMenu({ typed, names: [], active: -1, open: true, loading: true });
    void loadPublicRepos(prefix.owner).then(names => {
      if (!mounted.current || revision.current !== current || composing.current || input.disabled || input.readOnly ||
        inputRef.current !== input || input.ownerDocument.activeElement !== input || input.value !== typed) return;
      const matches = matchingRepos(prefix.partial, names);
      const candidate = inline && input.selectionStart === typed.length && input.selectionEnd === typed.length
        ? bestCompletion(prefix.partial, matches) : null;
      const active = candidate?.remainder ? 0 : -1;
      setMenu({ typed, names: matches, active, open: matches.length > 0, loading: false });
      if (candidate?.remainder) applyName(typed, candidate.name);
    });
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const typed = input.value;
    const native = event.nativeEvent as InputEvent;
    // controlled setter가 실행되기 전에 입력 종류·커서를 보존합니다.
    const allowed = canCompleteInput({ value: typed, inputType: native.inputType,
      isComposing: !!native.isComposing || composing.current,
      selectionStart: input.selectionStart, selectionEnd: input.selectionEnd });
    if (prefetchTimer.current) clearTimeout(prefetchTimer.current);
    completion.current = null;
    selection.current = null;
    setValue(typed);
    if (composing.current || native.isComposing) { revision.current++; setMenu(emptyMenu); return; }
    const prefix = parseRepoPrefix(typed);
    if (prefix) { request(typed, input, allowed); return; }
    revision.current++;
    setMenu(emptyMenu);
    const owner = parseRepoPrefix(`${typed}/`)?.owner;
    if (owner && !prefetched.current.has(owner.toLowerCase())) {
      prefetchTimer.current = setTimeout(() => {
        prefetched.current.add(owner.toLowerCase());
        void loadPublicRepos(owner);
      }, 350);
    }
  }

  function confirm(name: string) {
    const prefix = parseRepoPrefix(menu.typed);
    if (!prefix) return;
    const base = menu.typed.slice(0, menu.typed.length - prefix.partial.length);
    const input = inputRef.current;
    const full = base + name;
    revision.current++;
    completion.current = null;
    selection.current = { typed: full, full, start: full.length };
    setValue(full);
    setMenu(current => ({ ...current, open: false, active: -1 }));
    input?.focus();
    if (input?.value === full) { input.setSelectionRange(full.length, full.length); selection.current = null; }
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing || composing.current) return;
    const input = event.currentTarget;
    if (menu.open && menu.names.length && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const next = menu.active < 0 ? (event.key === "ArrowDown" ? 0 : menu.names.length - 1)
        : (menu.active + (event.key === "ArrowDown" ? 1 : -1) + menu.names.length) % menu.names.length;
      setMenu(current => ({ ...current, active: next }));
      applyName(menu.typed, menu.names[next]);
      return;
    }
    if (event.key === "Escape" && menu.open) {
      event.preventDefault(); revision.current++;
      setMenu(current => ({ ...current, open: false }));
      return;
    }
    if (event.key === "Enter" && menu.open && menu.active >= 0) {
      event.preventDefault(); confirm(menu.names[menu.active]); return;
    }
    const active = completion.current;
    const selected = active && input.value === active.full && input.selectionStart === active.start && input.selectionEnd === active.full.length;
    if (!selected || !["ArrowRight", "End", "Tab", "Escape"].includes(event.key)) return;
    event.preventDefault(); revision.current++;
    const full = event.key === "Escape" ? active.typed : active.full;
    completion.current = null;
    selection.current = { typed: full, full, start: full.length };
    setValue(full);
    setMenu(current => ({ ...current, open: false, active: -1 }));
    if (input.value === full) { input.setSelectionRange(full.length, full.length); selection.current = null; }
  }

  return {
    inputProps: {
      value, onChange, onKeyDown, role: "combobox" as const, "aria-autocomplete": "both" as const,
      "aria-expanded": menu.open, "aria-controls": listId,
      "aria-activedescendant": menu.open && menu.active >= 0 ? `${listId}-${menu.active}` : undefined,
      onFocus: () => {
        const input = inputRef.current;
        if (input && !input.disabled && parseRepoPrefix(input.value)) request(input.value, input, false);
      },
      onCompositionStart: () => { composing.current = true; revision.current++; completion.current = null; selection.current = null; setMenu(emptyMenu); },
      onCompositionEnd: () => { composing.current = false; },
      onBlur: () => { revision.current++; completion.current = null; selection.current = null; setMenu(current => ({ ...current, open: false })); },
    },
    listProps: { id: listId, ref: listRef, role: "listbox" as const, "aria-label": "공개 저장소 후보" },
    open: menu.open, loading: menu.loading, suggestions: menu.names, activeIndex: menu.active,
    partial: parseRepoPrefix(menu.typed)?.partial ?? "", select: confirm,
    optionId: (index: number) => `${listId}-${index}`,
    announcement: menu.open ? (menu.loading ? "저장소 목록 불러오는 중" : `후보 ${menu.names.length}개`) : "",
  };
}

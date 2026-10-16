"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export type SelectOption = { value: string; label: string; description?: string };

type UiSelectProps = {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  className?: string;
  disabled?: boolean;
  name?: string;
  placeholder?: string;
  required?: boolean;
};

/** 项目统一使用的键盘可操作选择器，避免 Windows/浏览器原生弹出菜单样式不一致。 */
export function UiSelect({
  value,
  options,
  onChange,
  ariaLabel,
  className = "",
  disabled = false,
  name,
  placeholder,
  required = false,
}: UiSelectProps) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selected = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) return;
    function closeOutside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setActiveIndex(index);
    setOpen(false);
    trigger.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      if (!open) {
        setOpen(true);
        setActiveIndex(selectedIndex);
      } else {
        setActiveIndex((current) => (current + direction + options.length) % options.length);
      }
    } else if (event.key === "Home" && open) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End" && open) {
      event.preventDefault();
      setActiveIndex(Math.max(options.length - 1, 0));
    } else if (event.key === "Enter" && open) {
      event.preventDefault();
      choose(activeIndex);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    } else if ((event.key === " " || event.key === "Enter") && !open) {
      event.preventDefault();
      setActiveIndex(selectedIndex);
      setOpen(true);
    }
  }

  return (
    <div className={`ui-select ${className}`} ref={root}>
      {name && <input type="hidden" name={name} value={value} />}
      <button
        ref={trigger}
        className="ui-select-trigger"
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-required={required || undefined}
        aria-controls={`${id}-options`}
        aria-activedescendant={open ? `${id}-option-${activeIndex}` : undefined}
        disabled={disabled}
        onClick={() => {
          setActiveIndex(selectedIndex);
          setOpen((current) => !current);
        }}
        onKeyDown={onKeyDown}
      >
        <span className={!selected ? "placeholder" : ""}>{selected?.label ?? placeholder ?? "请选择"}</span>
        <span className="ui-select-chevron" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="ui-select-menu" id={`${id}-options`} role="listbox" aria-label={ariaLabel}>
          {options.map((option, index) => (
            <button
              id={`${id}-option-${index}`}
              className={`ui-select-option ${value === option.value ? "selected" : ""} ${activeIndex === index ? "active" : ""}`}
              key={`${option.value}:${index}`}
              type="button"
              role="option"
              aria-selected={value === option.value}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(index)}
            >
              <span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>
              {value === option.value && <span className="ui-select-check" aria-hidden="true">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

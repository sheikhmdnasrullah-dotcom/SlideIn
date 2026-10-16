"use client";

import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { cn } from "@/lib/utils";

/**
 * FilterBar: URL-backed filters. A filter is part of the address, so a
 * filtered view is shareable and survives a reload — never component state.
 */
export interface FilterField {
  key: string;
  label: string;
  options: { value: string; label: string }[];
}

export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = "Search",
  fields = [],
  values = {},
  onFieldChange,
  onReset,
  resultCount,
  actions,
  className,
}: {
  search?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  fields?: FilterField[];
  values?: Record<string, string>;
  onFieldChange?: (key: string, value: string) => void;
  onReset?: () => void;
  resultCount?: number;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-rule px-6 py-3",
        className,
      )}
    >
      {onSearchChange && (
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 size-[18px] -translate-y-1/2 text-ink-faint"
            aria-hidden
          />
          <Input
            value={search ?? ""}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="w-56 pl-10"
          />
        </div>
      )}
      {fields.map((field) => (
        <Select
          key={field.key}
          value={values[field.key] ?? ""}
          onChange={(event) => onFieldChange?.(field.key, event.target.value)}
          aria-label={field.label}
          className="w-auto"
        >
          <option value="">{field.label}: all</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      ))}
      {typeof resultCount === "number" && (
        <span className="font-label text-ink-muted">{resultCount} shown</span>
      )}
      <div className="ml-auto flex items-center gap-2">
        {actions}
        {onReset && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="text-ink-muted"
            type="button"
          >
            <X className="size-3.5" aria-hidden />
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}

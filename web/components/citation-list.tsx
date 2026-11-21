"use client";

import type { Citation, CitationMeta } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CitationList({
  citations,
  messageId,
  activeIndex,
  meta,
  onSelect,
}: {
  citations: Citation[] | null;
  messageId?: string;
  activeIndex?: number | null;
  meta?: CitationMeta | null;
  onSelect?: (index: number) => void;
}) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2">
      {meta?.fallback ? (
        <p className="text-xs text-amber-600">
          回答未标注编号，以下为达到相关度阈值的片段
        </p>
      ) : null}
      {meta?.mode === "recomputed" ? (
        <p className="text-xs text-slate-500">
          按当前检索策略重算的候选引用
        </p>
      ) : null}
      {meta?.degraded ? (
        <p className="text-xs text-amber-600">
          精排不可用，本次引用未做相关度过滤
        </p>
      ) : null}
      {citations.map((citation, index) => {
        const label = citation.index ?? index + 1;
        const anchor = messageId
          ? `citation-${messageId}-${label}`
          : undefined;
        return (
          <button
            key={`${citation.document_id}-${citation.chunk_index}-${label}`}
            id={anchor}
            type="button"
            onClick={() => onSelect?.(label)}
            className={cn(
              "block w-full rounded-md border bg-white p-3 text-left text-xs transition",
              activeIndex === label
                ? "border-slate-900 ring-1 ring-slate-900"
                : "border-slate-200 hover:border-slate-300",
            )}
          >
            <div className="flex flex-wrap items-center gap-2 font-medium text-slate-700">
              <span>[{label}]</span>
              <span>{citation.document_title}</span>
              {citation.heading_path && citation.heading_path.length > 0 ? (
                <span className="text-slate-400">
                  {citation.heading_path.join(" > ")}
                </span>
              ) : null}
              {typeof citation.score === "number" ? (
                <span className="text-slate-400">
                  {citation.score.toFixed(3)}
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-slate-500">{citation.snippet}</p>
          </button>
        );
      })}
    </div>
  );
}

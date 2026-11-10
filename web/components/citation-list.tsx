"use client";

import type { Citation } from "@/lib/types";

export function CitationList({
  citations,
}: {
  citations: Citation[] | null;
}) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2">
      {citations.map((citation, index) => (
        <div
          key={`${citation.document_id}-${citation.chunk_index}`}
          className="rounded-md border border-slate-200 bg-white p-3 text-xs"
        >
          <div className="font-medium text-slate-700">
            [{index + 1}] {citation.document_title}
          </div>
          <p className="mt-1 text-slate-500">{citation.snippet}</p>
        </div>
      ))}
    </div>
  );
}

"use client";

import { ButtonSecondary } from "./ui";

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between text-sm text-slate-500">
      <span>共 {total} 条</span>
      <div className="flex items-center gap-2">
        <ButtonSecondary
          className="px-2 py-1 text-xs"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          上一页
        </ButtonSecondary>
        <span>
          {page} / {pages}
        </span>
        <ButtonSecondary
          className="px-2 py-1 text-xs"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          下一页
        </ButtonSecondary>
      </div>
    </div>
  );
}

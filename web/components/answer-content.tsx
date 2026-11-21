"use client";

export function AnswerContent({
  content,
  onCite,
}: {
  content: string;
  onCite?: (index: number) => void;
}) {
  const parts = content.split(/(\[\d{1,3}\])/g);
  return (
    <p className="whitespace-pre-wrap">
      {parts.map((part, position) => {
        const match = /^\[(\d{1,3})\]$/.exec(part);
        if (!match) {
          return <span key={position}>{part}</span>;
        }
        const index = Number(match[1]);
        return (
          <button
            key={position}
            type="button"
            className="mx-0.5 rounded bg-slate-200 px-1 text-xs text-slate-700 hover:bg-slate-300"
            aria-label={`跳转到引用 ${index}`}
            onClick={() => onCite?.(index)}
          >
            [{index}]
          </button>
        );
      })}
    </p>
  );
}

import type { ClaimVerification } from "@/lib/types";
import { VERDICT_COLORS, confidencePercent, formatMetric } from "@/lib/format";

export default function ClaimCard({ item }: { item: ClaimVerification }) {
  const color = VERDICT_COLORS[item.verdict] ?? VERDICT_COLORS.UNSUPPORTED;
  const evidence = item.evidence ?? [];

  return (
    <div
      className="rounded-md border border-zinc-200 border-l-4 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium leading-snug">{item.claim}</p>
        <span
          className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold text-white"
          style={{ backgroundColor: color }}
        >
          {item.verdict}
        </span>
      </div>

      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{item.reason}</p>
      <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
        method: {item.method}
      </p>

      {item.confidence !== null && item.confidence !== undefined && (
        <div className="mt-3 max-w-sm">
          <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400">
            <span>Confidence</span>
            <span>{confidencePercent(item.confidence)}%</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-1.5 rounded-full"
              style={{
                width: `${confidencePercent(item.confidence)}%`,
                backgroundColor: color,
              }}
            />
          </div>
        </div>
      )}

      {evidence.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer select-none text-sm font-medium text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100">
            Evidence ({evidence.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {evidence.map((ev, i) => (
              <li
                key={i}
                className="rounded-md bg-zinc-50 p-3 text-sm dark:bg-zinc-800/50"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="font-semibold text-zinc-700 dark:text-zinc-200">
                    {ev.doc}
                  </span>
                  <span>hybrid {formatMetric(ev.hybrid_score)}</span>
                  <span>bm25 {formatMetric(ev.bm25_score)}</span>
                  <span>vector {formatMetric(ev.vector_score)}</span>
                </div>
                <p className="mt-1.5 whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">
                  {ev.text}
                </p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

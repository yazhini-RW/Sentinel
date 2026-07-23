import type { RunLog, Verdict } from "@/lib/types";
import { VERDICT_COLORS, formatDate } from "@/lib/format";
import ClaimCard from "./ClaimCard";
import TrustGauge from "./TrustGauge";

const VERDICT_ORDER: Verdict[] = ["SUPPORTED", "CONTRADICTED", "UNSUPPORTED"];

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm text-zinc-700 dark:text-zinc-300">{value}</dd>
    </div>
  );
}

export default function ResultsView({ run }: { run: RunLog }) {
  const counts = run.result?.verdict_counts ?? {
    SUPPORTED: 0,
    CONTRADICTED: 0,
    UNSUPPORTED: 0,
  };
  const claims = run.steps?.verification ?? [];
  const documents = run.steps?.index?.documents ?? [];
  const trustScore = run.result?.trust_score ?? null;

  return (
    <div className="space-y-6">
      {/* Summary card */}
      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
          <TrustGauge score={trustScore} />
          <div className="min-w-0 flex-1 space-y-4">
            {trustScore === null && (
              <p className="rounded-md bg-zinc-100 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                No trust score — no claims could be extracted from the answer.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {VERDICT_ORDER.map((verdict) => (
                <span
                  key={verdict}
                  className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 px-3 py-1 text-sm dark:border-zinc-700"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: VERDICT_COLORS[verdict] }}
                  />
                  <span className="text-zinc-600 dark:text-zinc-400">{verdict}</span>
                  <span className="font-semibold">{counts[verdict] ?? 0}</span>
                </span>
              ))}
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
              <MetaItem label="Verifier" value={run.config?.verifier ?? "?"} />
              <MetaItem label="Top-k" value={String(run.config?.top_k ?? "?")} />
              <MetaItem
                label="Elapsed"
                value={
                  typeof run.result?.elapsed_seconds === "number"
                    ? `${run.result.elapsed_seconds.toFixed(1)}s`
                    : "?"
                }
              />
              <MetaItem label="Run" value={run.run_id} />
              <MetaItem label="Date" value={formatDate(run.timestamp)} />
              <MetaItem
                label="Index"
                value={`${documents.length} doc${documents.length === 1 ? "" : "s"}, ${
                  run.steps?.index?.num_chunks ?? "?"
                } chunks`}
              />
            </dl>
            {documents.length > 0 && (
              <p className="text-xs text-zinc-400 dark:text-zinc-500">
                Documents: {documents.join(", ")}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Question and answer */}
      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
          Question
        </h2>
        <p className="mt-1 text-sm">{run.input?.question}</p>
        <h2 className="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
          Answer under verification
        </h2>
        <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
          {run.input?.answer}
        </p>
      </section>

      {/* Claims */}
      <section>
        <h2 className="mb-3 text-base font-semibold">
          Claims ({claims.length})
        </h2>
        {claims.length === 0 ? (
          <p className="rounded-md border border-zinc-200 bg-white px-4 py-6 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
            No claims were extracted from this answer.
          </p>
        ) : (
          <div className="space-y-3">
            {claims.map((item, i) => (
              <ClaimCard key={i} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

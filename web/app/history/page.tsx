"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Spinner from "@/components/Spinner";
import { errorMessage, getRuns } from "@/lib/api";
import {
  VERDICT_COLORS,
  formatDate,
  formatScore,
  scoreColor,
  truncate,
} from "@/lib/format";
import type { RunSummary } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; runs: RunSummary[] };

export default function HistoryPage() {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getRuns()
      .then((runs) => {
        if (!cancelled) setState({ status: "loaded", runs });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: "error", message: errorMessage(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const retry = () => {
    setState({ status: "loading" });
    setReloadKey((k) => k + 1);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">History</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Past verification runs, newest first.
        </p>
      </div>

      {state.status === "loading" && (
        <div className="flex items-center gap-3 py-12 text-zinc-500 dark:text-zinc-400">
          <Spinner />
          <span className="text-sm">Loading runs…</span>
        </div>
      )}

      {state.status === "error" && (
        <ErrorBanner message={state.message} onRetry={retry} />
      )}

      {state.status === "loaded" && state.runs.length === 0 && (
        <div className="rounded-lg border border-dashed border-zinc-300 px-4 py-12 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No runs yet.
          </p>
          <Link
            href="/"
            className="mt-2 inline-block text-sm font-medium text-emerald-600 hover:underline dark:text-emerald-400"
          >
            Verify your first answer →
          </Link>
        </div>
      )}

      {state.status === "loaded" && state.runs.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
              <tr>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Question</th>
                <th className="px-4 py-3 font-medium">Verifier</th>
                <th className="px-4 py-3 font-medium">Score</th>
                <th className="px-4 py-3 font-medium">Verdicts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {state.runs.map((run) => (
                <tr
                  key={run.run_id}
                  onClick={() => router.push(`/runs/${run.run_id}`)}
                  className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900"
                >
                  <td className="whitespace-nowrap px-4 py-3 text-zinc-500 dark:text-zinc-400">
                    {formatDate(run.timestamp)}
                  </td>
                  <td className="max-w-md px-4 py-3">
                    <Link
                      href={`/runs/${run.run_id}`}
                      className="block truncate font-medium hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {truncate(run.question, 90)}
                    </Link>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-zinc-500 dark:text-zinc-400">
                    {run.verifier}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span
                      className="font-semibold"
                      style={{ color: scoreColor(run.trust_score) }}
                    >
                      {formatScore(run.trust_score)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="inline-flex gap-2 text-xs font-semibold">
                      <span style={{ color: VERDICT_COLORS.SUPPORTED }}>
                        S {run.verdict_counts?.SUPPORTED ?? 0}
                      </span>
                      <span style={{ color: VERDICT_COLORS.CONTRADICTED }}>
                        C {run.verdict_counts?.CONTRADICTED ?? 0}
                      </span>
                      <span style={{ color: VERDICT_COLORS.UNSUPPORTED }}>
                        U {run.verdict_counts?.UNSUPPORTED ?? 0}
                      </span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import ResultsView from "@/components/ResultsView";
import Spinner from "@/components/Spinner";
import { errorMessage, getRun } from "@/lib/api";
import type { RunLog } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; id: string; message: string }
  | { status: "loaded"; id: string; run: RunLog };

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id;
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    getRun(runId)
      .then((run) => {
        if (!cancelled) setState({ status: "loaded", id: runId, run });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({ status: "error", id: runId, message: errorMessage(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, reloadKey]);

  const retry = () => {
    setState({ status: "loading" });
    setReloadKey((k) => k + 1);
  };

  // Treat state for a different run id as still loading (param changed).
  const current =
    state.status !== "loading" && state.id === runId ? state : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="min-w-0 truncate text-2xl font-bold tracking-tight">
          Run{" "}
          <span className="font-mono text-lg text-zinc-500 dark:text-zinc-400">
            {runId}
          </span>
        </h1>
        <Link
          href="/history"
          className="shrink-0 text-sm font-medium text-emerald-600 hover:underline dark:text-emerald-400"
        >
          ← Back to history
        </Link>
      </div>

      {current === null && (
        <div className="flex items-center gap-3 py-12 text-zinc-500 dark:text-zinc-400">
          <Spinner />
          <span className="text-sm">Loading run…</span>
        </div>
      )}

      {current?.status === "error" && (
        <ErrorBanner message={current.message} onRetry={retry} />
      )}

      {current?.status === "loaded" && <ResultsView run={current.run} />}
    </div>
  );
}

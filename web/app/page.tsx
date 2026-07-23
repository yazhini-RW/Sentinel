"use client";

import { useEffect, useRef, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import ResultsView from "@/components/ResultsView";
import Spinner from "@/components/Spinner";
import { errorMessage, getHealth, verify } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { RunLog, VerifierOption } from "@/lib/types";

const MAX_FILES = 20;
const MAX_FILE_BYTES = 2 * 1024 * 1024; // 2 MB
const ALLOWED_EXTENSIONS = [".txt", ".md"];
const VERIFIERS: VerifierOption[] = ["auto", "nli", "mock", "gemini"];

const inputClass =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm " +
  "focus:outline-none focus:ring-2 focus:ring-emerald-500 " +
  "dark:border-zinc-700 dark:bg-zinc-900";

function validateFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `${file.name}: only .txt and .md files are allowed`;
  }
  if (file.size > MAX_FILE_BYTES) {
    return `${file.name}: exceeds the 2 MB per-file limit`;
  }
  return null;
}

export default function VerifyPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [verifier, setVerifier] = useState<VerifierOption>("auto");
  const [topK, setTopK] = useState("3");
  const [files, setFiles] = useState<File[]>([]);
  const [sourcesPath, setSourcesPath] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RunLog | null>(null);
  // null = not checked yet; assume allowed so the field isn't hidden by
  // default while /health is loading (matches the API's own default).
  const [allowSourcesPath, setAllowSourcesPath] = useState<boolean | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (!cancelled) setAllowSourcesPath(h.allow_sources_path);
      })
      .catch(() => {
        // API unreachable — the submit button's own error handling covers
        // this; default to showing the field rather than hiding it silently.
        if (!cancelled) setAllowSourcesPath(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleFilesSelected = (list: FileList | null) => {
    if (!list) return;
    const problems: string[] = [];
    const next = [...files];
    for (const file of Array.from(list)) {
      const problem = validateFile(file);
      if (problem) {
        problems.push(problem);
        continue;
      }
      if (next.some((f) => f.name === file.name && f.size === file.size)) {
        continue; // already selected
      }
      if (next.length >= MAX_FILES) {
        problems.push(`At most ${MAX_FILES} files are allowed`);
        break;
      }
      next.push(file);
    }
    setFiles(next);
    setFileError(problems.length > 0 ? problems.join(". ") : null);
    // Reset the input so selecting the same file again re-triggers onChange.
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (target: File) => {
    setFiles((prev) => prev.filter((f) => f !== target));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const q = question.trim();
    const a = answer.trim();
    const path = sourcesPath.trim();

    if (!q || !a) {
      setError("Both a question and an answer are required.");
      return;
    }
    if (files.length === 0 && !path) {
      setError(
        "Provide source documents — upload .txt/.md files or enter a folder path on the API server.",
      );
      return;
    }
    const parsedK = Number(topK);
    const k = Number.isFinite(parsedK)
      ? Math.min(20, Math.max(1, Math.round(parsedK)))
      : 3;

    setSubmitting(true);
    setResult(null);
    try {
      const run = await verify({
        question: q,
        answer: a,
        verifier,
        topK: k,
        files,
        sourcesPath: path,
      });
      setResult(run);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Verify an answer</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Sentinel splits the answer into claims and checks each one against
          your source documents.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        <div>
          <label htmlFor="question" className="mb-1 block text-sm font-medium">
            Question
          </label>
          <input
            id="question"
            type="text"
            className={inputClass}
            placeholder="What was the question the answer responds to?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={submitting}
          />
        </div>

        <div>
          <label htmlFor="answer" className="mb-1 block text-sm font-medium">
            Answer to verify
          </label>
          <textarea
            id="answer"
            rows={6}
            className={inputClass}
            placeholder="Paste the AI-generated answer here…"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={submitting}
          />
        </div>

        <div className="flex flex-wrap gap-4">
          <div className="w-40">
            <label htmlFor="verifier" className="mb-1 block text-sm font-medium">
              Verifier
            </label>
            <select
              id="verifier"
              className={inputClass}
              value={verifier}
              onChange={(e) => setVerifier(e.target.value as VerifierOption)}
              disabled={submitting}
            >
              {VERIFIERS.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div className="w-32">
            <label htmlFor="top-k" className="mb-1 block text-sm font-medium">
              Top-k
            </label>
            <input
              id="top-k"
              type="number"
              min={1}
              max={20}
              step={1}
              className={inputClass}
              value={topK}
              onChange={(e) => setTopK(e.target.value)}
              disabled={submitting}
            />
          </div>
        </div>

        <fieldset className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
          <legend className="px-1 text-sm font-semibold">
            Source documents
          </legend>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            At least one source is required: upload files, enter a folder path
            on the machine running the API, or both.
          </p>

          <div>
            <label htmlFor="files" className="mb-1 block text-sm font-medium">
              Upload files (.txt / .md, up to {MAX_FILES} files, 2 MB each)
            </label>
            <input
              id="files"
              ref={fileInputRef}
              type="file"
              multiple
              accept=".txt,.md,text/plain,text/markdown"
              onChange={(e) => handleFilesSelected(e.target.files)}
              disabled={submitting}
              className="block w-full text-sm text-zinc-600 file:mr-3 file:rounded-md file:border-0 file:bg-emerald-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-emerald-700 dark:text-zinc-400"
            />
            {files.length > 0 && (
              <ul className="mt-2 space-y-1">
                {files.map((f) => (
                  <li
                    key={`${f.name}-${f.size}`}
                    className="flex items-center gap-2 text-sm"
                  >
                    <span className="truncate">{f.name}</span>
                    <span className="shrink-0 text-xs text-zinc-400">
                      {formatBytes(f.size)}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(f)}
                      disabled={submitting}
                      className="shrink-0 text-xs text-red-600 hover:underline dark:text-red-400"
                    >
                      remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {fileError && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                {fileError}
              </p>
            )}
          </div>

          {allowSourcesPath !== false && (
            <div className="mt-4">
              <label
                htmlFor="sources-path"
                className="mb-1 block text-sm font-medium"
              >
                …or a folder path on the API server
              </label>
              <input
                id="sources-path"
                type="text"
                className={inputClass}
                placeholder="e.g. C:\docs\sources or ./samples"
                value={sourcesPath}
                onChange={(e) => setSourcesPath(e.target.value)}
                disabled={submitting}
              />
            </div>
          )}
        </fieldset>

        {error && <ErrorBanner message={error} />}

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting && <Spinner className="h-4 w-4" />}
            {submitting ? "Verifying…" : "Verify"}
          </button>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {submitting
              ? "Running claim extraction and verification — this can take 10–60 seconds."
              : "A verification typically takes 10–60 seconds."}
          </p>
        </div>
      </form>

      {result && (
        <div>
          <h2 className="mb-4 text-xl font-bold tracking-tight">Result</h2>
          <ResultsView run={result} />
        </div>
      )}
    </div>
  );
}

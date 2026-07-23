import type { Verdict } from "./types";

/** Exact verdict colors from the product spec. */
export const VERDICT_COLORS: Record<Verdict, string> = {
  SUPPORTED: "#16a34a",
  CONTRADICTED: "#dc2626",
  UNSUPPORTED: "#6b7280",
};

/** Trust-score color: green >= 80, amber >= 50, red below, grey for n/a. */
export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#6b7280";
  if (score >= 80) return "#16a34a";
  if (score >= 50) return "#d97706";
  return "#dc2626";
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "n/a";
  return String(Math.round(score));
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** Formats a retrieval metric to 3 decimals, tolerating missing values. */
export function formatMetric(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(3)
    : "–";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function truncate(text: string, max = 90): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/**
 * Normalizes a confidence value to a 0-100 percentage.
 * The backend reports 0-1 floats; values > 1 are treated as percentages.
 */
export function confidencePercent(confidence: number): number {
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  return Math.max(0, Math.min(100, Math.round(pct)));
}

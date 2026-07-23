import type {
  HealthResponse,
  RunLog,
  RunSummary,
  VerifierOption,
} from "./types";

/** Base URL of the Sentinel FastAPI backend. */
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export const API_UNREACHABLE_MESSAGE =
  "API not reachable — start it with: sentinel serve";

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

/** Extracts a human-readable message from any thrown value. */
export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // Network-level failure: backend is not running / not reachable.
    throw new ApiError(API_UNREACHABLE_MESSAGE);
  }

  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const data: unknown = await res.json();
      if (
        data !== null &&
        typeof data === "object" &&
        "detail" in data &&
        typeof (data as { detail: unknown }).detail === "string"
      ) {
        detail = (data as { detail: string }).detail;
      }
    } catch {
      // Body was not JSON; keep the generic message.
    }
    throw new ApiError(detail, res.status);
  }

  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function getRuns(limit = 50): Promise<RunSummary[]> {
  return request<RunSummary[]>(`/runs?limit=${limit}`);
}

export function getRun(runId: string): Promise<RunLog> {
  return request<RunLog>(`/runs/${encodeURIComponent(runId)}`);
}

export interface VerifyRequest {
  question: string;
  answer: string;
  verifier: VerifierOption;
  topK: number;
  files: File[];
  sourcesPath?: string;
}

export function verify(req: VerifyRequest): Promise<RunLog> {
  const form = new FormData();
  form.set("question", req.question);
  form.set("answer", req.answer);
  form.set("verifier", req.verifier);
  form.set("top_k", String(req.topK));
  const path = req.sourcesPath?.trim();
  if (path) form.set("sources_path", path);
  for (const file of req.files) form.append("files", file);
  return request<RunLog>("/verify", { method: "POST", body: form });
}

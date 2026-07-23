/** Types mirroring the Sentinel FastAPI backend responses. */

export type Verdict = "SUPPORTED" | "CONTRADICTED" | "UNSUPPORTED";

export type VerifierOption = "auto" | "gemini" | "nli" | "mock";

export interface VerdictCounts {
  SUPPORTED: number;
  CONTRADICTED: number;
  UNSUPPORTED: number;
}

export interface HealthResponse {
  status: string;
  default_verifier: "nli" | "gemini" | "mock";
  allow_sources_path: boolean;
}

export interface Evidence {
  doc: string;
  text: string;
  bm25_score: number;
  vector_score: number;
  hybrid_score: number;
}

export interface ClaimVerification {
  claim: string;
  verdict: Verdict;
  reason: string;
  method: string;
  /** Can be null when the verifier does not report a confidence. */
  confidence: number | null;
  evidence: Evidence[];
}

export interface RunLog {
  run_id: string;
  timestamp: string;
  input: {
    question: string;
    answer: string;
    sources_folder: string;
  };
  config: {
    top_k: number;
    verifier: string;
  };
  steps: {
    index: {
      documents: string[];
      num_chunks: number;
      embedder: string;
    };
    claim_splitting: {
      method: string;
      claims: string[];
    };
    verification: ClaimVerification[];
  };
  result: {
    /** Null when no claims were extracted from the answer. */
    trust_score: number | null;
    verdict_counts: VerdictCounts;
    elapsed_seconds: number;
  };
}

/** One row from GET /runs. */
export interface RunSummary {
  run_id: string;
  timestamp: string;
  trust_score: number | null;
  verdict_counts: VerdictCounts;
  question: string;
  verifier: string;
}

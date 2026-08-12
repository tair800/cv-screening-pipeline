import type {
  Audit,
  CandidateDetail,
  CandidateList,
  Decision,
  DecisionLog,
  Health,
} from "./types";

/** Thrown for any non-2xx response, carrying the server's own message where it sent one. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  // FastAPI puts the reason in `detail`; keep it rather than replacing it with a generic
  // message, because the server's refusal usually says exactly what to fix.
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
  } catch {
    /* fall through to the status text */
  }
  return response.statusText || `request failed with ${response.status}`;
}

export const api = {
  health: () => get<Health>("/api/health"),
  candidates: () => get<CandidateList>("/api/candidates"),
  candidate: (cvId: string) => get<CandidateDetail>(`/api/candidates/${cvId}`),
  audit: () => get<Audit>("/api/audit"),
  decisions: () => get<DecisionLog>("/api/decisions"),

  async decide(
    cvId: string,
    body: { decision: Decision; actor: string; reason: string; idempotency_key?: string },
  ) {
    const response = await fetch(`/api/candidates/${cvId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new ApiError(await readError(response), response.status);
    }
    return (await response.json()) as { appended: boolean };
  },
};

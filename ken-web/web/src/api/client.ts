// Typed fetch wrapper over the ken-web API. Same-origin: paths are relative
// (`/api/...`) so the Vite dev proxy or the prod static mount both work.
//
// Tests mock THIS module (vi.mock("../api/client")) — no network in tests.

import type {
  Artifact,
  ArtifactDetail,
  AttemptRequest,
  AttemptResult,
  Coverage,
  Due,
} from "../types";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

/** Raised when the API responds with a non-2xx status. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (cause) {
    throw new ApiError(0, `network error reaching ${path}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  // 204 / empty bodies are not expected on this surface, but guard anyway.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** GET /api/artifacts — all registered artifacts with status + weak_count. */
export function getArtifacts(): Promise<Artifact[]> {
  return request<Artifact[]>("/api/artifacts");
}

/** POST /api/artifacts — register a new artifact by path. */
export function registerArtifact(path: string): Promise<Artifact> {
  return request<Artifact>("/api/artifacts", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ path }),
  });
}

/** GET /api/artifacts/{id}/due — generates+saves questions if missing/stale. */
export function getDue(artifactId: string): Promise<Due> {
  return request<Due>(`/api/artifacts/${encodeURIComponent(artifactId)}/due`);
}

/** POST /api/attempts — single-question grade + record; remediation on fail. */
export function postAttempt(req: AttemptRequest): Promise<AttemptResult> {
  return request<AttemptResult>("/api/attempts", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(req),
  });
}

/** GET /api/coverage — the headline coverage report. */
export function getCoverage(): Promise<Coverage> {
  return request<Coverage>("/api/coverage");
}

/** GET /api/artifacts/{id}/detail — read-only per-question schedule rows (no generation). */
export function getArtifactDetail(artifactId: string): Promise<ArtifactDetail> {
  return request<ArtifactDetail>(`/api/artifacts/${encodeURIComponent(artifactId)}/detail`);
}

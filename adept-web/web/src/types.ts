// Wire DTOs — mirror adept-web/api/src/khala/adept_web/schemas.py exactly.
// Keep these in lockstep with the FastAPI contract.

/** MeOut — the current session identity. */
export interface Me {
  email: string;
}

/** ArtifactOut — one row per registered artifact. status: "vouched" | "orphan". */
export interface Artifact {
  artifact_id: string;
  path: string;
  status: "vouched" | "orphan";
  weak_count: number;
}

/** QuestionOut — a single due question. */
export interface Question {
  question_id: string;
  text: string;
}

/** DueOut — the questions currently due for an artifact. */
export interface Due {
  questions: Question[];
}

/** AttemptReq — POST /api/attempts body. person is server-derived from the session. */
export interface AttemptRequest {
  artifact_id: string;
  question_id: string;
  answer: string;
}

/** AttemptOut — the grade result. remediation present only on fail (may still be null). */
export interface AttemptResult {
  passed: boolean;
  score: number;
  remediation: string | null;
}

/** WeaknessOut — a repeatedly-failed question. */
export interface Weakness {
  question_id: string;
  artifact_id: string;
  fail_count: number;
}

/** CoverageOut — the headline coverage report. */
export interface Coverage {
  total: number;
  covered: number;
  ratio: number;
  orphans: string[];
  weakness: Weakness[];
}

/** QuestionDetailOut — one per-question schedule row. next_due null ⇒ never-attempted ⇒ due now. */
export interface QuestionDetail {
  question_id: string;
  text: string;
  rung: number;            // 0..4, index into the ladder [now,1d,3d,7d,30d]
  attempted: boolean;
  last_passed: boolean | null;
  last_ts: string | null;
  fail_count: number;
  next_due: string | null;
  due: boolean;
}

/** ArtifactDetailOut — all per-question rows for one artifact. */
export interface ArtifactDetail {
  questions: QuestionDetail[];
}

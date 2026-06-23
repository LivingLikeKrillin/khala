// Wire DTOs — mirror ken-web/api/src/ken_web_api/schemas.py exactly.
// Keep these in lockstep with the FastAPI contract.

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

/** AttemptReq — POST /api/attempts body. `person` is informational this slice. */
export interface AttemptRequest {
  artifact_id: string;
  question_id: string;
  person: string;
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

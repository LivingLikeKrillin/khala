import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { getArtifacts, getDue, postAttempt } from "../api/client";
import type { Question } from "../types";
import ProgressBar from "../components/ProgressBar";
import QuestionCard from "../components/QuestionCard";
import RemediationPanel from "../components/RemediationPanel";

type Phase =
  | "loading"
  | "error"
  | "empty" // nothing due
  | "answering" // showing the current question's input
  | "grading" // awaiting the grade
  | "passed" // brief pass affirmation before auto-advance
  | "remediating" // failed: showing the panel until acknowledged
  | "summary";

/** A short display name for the artifact (last path segment). */
function basename(p: string): string {
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

export default function Review() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const artifactId = params.get("artifact") ?? "";

  const [phase, setPhase] = useState<Phase>("loading");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [artifactName, setArtifactName] = useState<string>(artifactId);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [idx, setIdx] = useState(0);
  const [remediation, setRemediation] = useState<string | null>(null);

  // session tally
  const [vouched, setVouched] = useState(0);
  const [requeued, setRequeued] = useState(0);

  // --- load due questions on mount / artifact change ---
  useEffect(() => {
    let alive = true;
    if (!artifactId) {
      setPhase("error");
      setErrorMsg("No artifact selected.");
      return;
    }
    setPhase("loading");
    (async () => {
      try {
        // artifact name is best-effort; never blocks the review.
        getArtifacts()
          .then((arts) => {
            const found = arts.find((a) => a.artifact_id === artifactId);
            if (alive && found) setArtifactName(basename(found.path));
          })
          .catch(() => {
            /* name is decorative */
          });

        const due = await getDue(artifactId);
        if (!alive) return;
        setQuestions(due.questions);
        setIdx(0);
        setVouched(0);
        setRequeued(0);
        setPhase(due.questions.length === 0 ? "empty" : "answering");
      } catch (err) {
        if (!alive) return;
        setErrorMsg(err instanceof Error ? err.message : "Failed to load questions.");
        setPhase("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [artifactId]);

  const total = questions.length;
  const current = questions[idx];
  const isLast = idx >= total - 1;

  const advance = useCallback(() => {
    if (isLast) {
      setPhase("summary");
    } else {
      setIdx((i) => i + 1);
      setRemediation(null);
      setPhase("answering");
    }
  }, [isLast]);

  async function handleSubmit(answer: string) {
    if (!current) return;
    setPhase("grading");
    try {
      const res = await postAttempt({
        artifact_id: artifactId,
        question_id: current.question_id,
        person: "kr", // informational this slice
        answer,
      });
      if (res.passed) {
        setVouched((v) => v + 1);
        setPhase("passed");
        // brief affirmation, then auto-advance
        window.setTimeout(() => advance(), 850);
      } else {
        setRequeued((r) => r + 1);
        setRemediation(res.remediation);
        setPhase("remediating");
      }
    } catch (err) {
      // Grading is fail-closed server-side; a transport error here is rare.
      // Surface it without losing the session.
      setErrorMsg(err instanceof Error ? err.message : "Could not grade your answer.");
      setPhase("error");
    }
  }

  // ---------------------------------------------------------------- render --
  if (phase === "loading") {
    return (
      <div className="review">
        <div className="progress skeleton" style={{ height: 3, margin: "16px 0 52px" }} />
        <div className="skeleton" style={{ height: 22, width: "30%", marginBottom: 28 }} />
        <div className="skeleton" style={{ height: 90, width: "85%", marginBottom: 36 }} />
        <div className="skeleton" style={{ height: 150, borderRadius: 14 }} />
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="state">
        <div className="state__icon">…</div>
        <h2>Something interrupted the session</h2>
        <p>{errorMsg}</p>
        <Link to="/" className="btn btn--ghost">
          Back to overview
        </Link>
      </div>
    );
  }

  if (phase === "empty") {
    return (
      <div className="state">
        <div className="state__icon">✓</div>
        <h2>Nothing due — you&rsquo;re square</h2>
        <p>
          There are no questions due for <b>{artifactName}</b> right now. Come
          back when this artifact resurfaces.
        </p>
        <Link to="/" className="btn btn--primary">
          Back to overview
        </Link>
      </div>
    );
  }

  if (phase === "summary") {
    return (
      <section className="summary" role="region" aria-label="Session summary">
        <div className="summary__seal" aria-hidden="true">
          ❧
        </div>
        <h1>Session complete</h1>
        <p className="summary__sub">
          You worked through {total} {total === 1 ? "question" : "questions"} on{" "}
          {artifactName}. Every answer you reviewed comes back next session.
        </p>
        <div className="summary__grid">
          <div className="stat stat--pass">
            <div className="n">{vouched}</div>
            <div className="l">vouched this session</div>
          </div>
          <div className="stat stat--requeue">
            <div className="n">{requeued}</div>
            <div className="l">queued for next session</div>
          </div>
        </div>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => navigate("/")}
        >
          Back to overview
        </button>
      </section>
    );
  }

  // active question phases: answering / grading / passed / remediating
  return (
    <div className="review">
      <div className="review__top">
        <span className="review__artifact">{artifactName}</span>
      </div>
      <ProgressBar current={idx + 1} total={total} />

      {phase === "passed" ? (
        <div className="verdict-pass" role="status" aria-live="polite">
          <span className="mark" aria-hidden="true">
            ✓
          </span>
          <div>
            <b>Vouched.</b> <span>That holds up — moving on.</span>
          </div>
        </div>
      ) : phase === "remediating" ? (
        <RemediationPanel
          remediation={remediation}
          isLast={isLast}
          onAcknowledge={advance}
        />
      ) : (
        current && (
          <QuestionCard
            question={current}
            index={idx + 1}
            total={total}
            grading={phase === "grading"}
            onSubmit={handleSubmit}
          />
        )
      )}
    </div>
  );
}

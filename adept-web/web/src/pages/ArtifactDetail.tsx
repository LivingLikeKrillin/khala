import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getArtifactDetail } from "../api/client";
import type { ArtifactDetail as ArtifactDetailType, QuestionDetail } from "../types";
import MasteryLadder from "../components/MasteryLadder";

type Status = "loading" | "ready" | "error";

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function QuestionRow({ q }: { q: QuestionDetail }) {
  const isOverdue = q.due && q.attempted;
  const isDueNow = !q.attempted && q.due;

  return (
    <div className="row row--static" style={{ flexDirection: "column", alignItems: "flex-start", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, width: "100%", flexWrap: "wrap" }}>
        <MasteryLadder rung={q.rung} />
        {isOverdue && (
          <span className="pill pill--orphan">overdue</span>
        )}
        {isDueNow && (
          <span className="pill pill--orphan">due now</span>
        )}
        {q.fail_count > 0 && (
          <span className="pill pill--weak">{q.fail_count} fail{q.fail_count !== 1 ? "s" : ""}</span>
        )}
      </div>
      <p style={{ margin: 0, fontFamily: "var(--serif)", fontSize: 17, lineHeight: 1.5 }}>
        {q.text}
      </p>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {q.attempted ? (
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--paper-ghost)" }}>
            {q.last_passed ? "✓ passed" : "✗ failed"}
            {q.last_ts ? ` · ${formatTs(q.last_ts)}` : ""}
          </span>
        ) : (
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--paper-ghost)" }}>
            never attempted
          </span>
        )}
        {q.next_due && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--paper-faint)" }}>
            next due: {formatTs(q.next_due)}
          </span>
        )}
      </div>
    </div>
  );
}

export default function ArtifactDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [detail, setDetail] = useState<ArtifactDetailType | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    (async () => {
      try {
        const data = await getArtifactDetail(id);
        if (!alive) return;
        setDetail(data);
        setStatus("ready");
      } catch (err) {
        if (!alive) return;
        setErrorMsg(err instanceof Error ? err.message : "Failed to load.");
        setStatus("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [id]);

  if (status === "loading") {
    return (
      <>
        <div className="skeleton" style={{ height: 32, width: "60%", marginBottom: 14 }} />
        <div className="skeleton" style={{ height: 20, width: "40%", marginBottom: 32 }} />
        <div className="stack">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 90, borderRadius: 14 }} />
          ))}
        </div>
      </>
    );
  }

  if (status === "error") {
    return (
      <div className="state">
        <div className="state__icon">…</div>
        <h2>Couldn&rsquo;t load artifact detail</h2>
        <p>{errorMsg}</p>
        <Link to="/" className="btn btn--ghost">Back to overview</Link>
      </div>
    );
  }

  const questions = detail?.questions ?? [];

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 32, flexWrap: "wrap" }}>
        <div>
          <div className="eyebrow" style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--paper-ghost)", marginBottom: 4 }}>
            artifact
          </div>
          <h1 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: "clamp(22px, 3.5vw, 32px)", margin: 0, letterSpacing: "-0.02em" }}>
            {id}
          </h1>
        </div>
        <Link
          to={`/review?artifact=${encodeURIComponent(id)}`}
          className="btn btn--primary"
        >
          Start review →
        </Link>
      </div>

      <div className="section-head" style={{ marginBottom: 16 }}>
        <span className="section-head__lead">
          <h2>Questions</h2>
          <span className="sub">{questions.length} {questions.length === 1 ? "question" : "questions"}</span>
        </span>
      </div>

      {questions.length === 0 ? (
        <div className="state" style={{ padding: "48px 0" }}>
          <div className="state__icon">?</div>
          <p>No current questions — start a review to generate them.</p>
        </div>
      ) : (
        <div className="stack">
          {questions.map((q) => (
            <QuestionRow key={q.question_id} q={q} />
          ))}
        </div>
      )}
    </>
  );
}

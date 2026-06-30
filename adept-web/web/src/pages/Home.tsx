import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getArtifacts, getCoverage } from "../api/client";
import type { Artifact, Coverage } from "../types";
import CoverageBadge from "../components/CoverageBadge";

function basename(p: string): string {
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

type Status = "loading" | "ready" | "error";

export default function Home() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [cov, arts] = await Promise.all([getCoverage(), getArtifacts()]);
        if (!alive) return;
        setCoverage(cov);
        setArtifacts(arts);
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
  }, []);

  function review(artifactId: string) {
    navigate(`/review?artifact=${encodeURIComponent(artifactId)}`);
  }

  // attention: orphans first, then weak (by weak_count), then the rest.
  const attention = [...artifacts].sort((a, b) => {
    const rank = (x: Artifact) => (x.status === "orphan" ? 0 : x.weak_count > 0 ? 1 : 2);
    const d = rank(a) - rank(b);
    return d !== 0 ? d : b.weak_count - a.weak_count;
  });

  const firstOrphan =
    coverage?.orphans?.[0] ?? attention.find((a) => a.status === "orphan")?.artifact_id;
  const startTarget = firstOrphan ?? attention[0]?.artifact_id;

  if (status === "loading") {
    return (
      <>
        <div className="skeleton" style={{ height: 60, width: "70%", marginBottom: 18 }} />
        <div className="skeleton" style={{ height: 24, width: "45%", marginBottom: 40 }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 22, marginBottom: 56 }} />
        <div className="stack">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 70, borderRadius: 14 }} />
          ))}
        </div>
      </>
    );
  }

  if (status === "error") {
    return (
      <div className="state">
        <div className="state__icon">…</div>
        <h2>Couldn&rsquo;t reach the substrate</h2>
        <p>{errorMsg}</p>
      </div>
    );
  }

  return (
    <>
      <section className="cover">
        <div className="eyebrow cover__eyebrow">Cognitive debt · repayment</div>
        <h1 className="cover__line">
          Pay down what you <em>owe</em> yourself.
        </h1>
        <p className="cover__sub">
          One grounded question at a time. Answer in your own words, get an honest
          read, and watch your coverage climb.
        </p>
        <div className="cover__cta">
          <button
            type="button"
            className="btn btn--primary"
            disabled={!startTarget}
            onClick={() => startTarget && review(startTarget)}
          >
            Start review →
          </button>
          {startTarget ? (
            <span className="cover__hint">
              next up: the first artifact that needs vouching
            </span>
          ) : (
            <span className="cover__hint">nothing to review — register an artifact</span>
          )}
        </div>
      </section>

      {coverage && <CoverageBadge coverage={coverage} />}

      <div className="section-head">
        <span className="section-head__lead">
          <h2>Needs your attention</h2>
          <span className="sub">orphans first, then artifacts with weak answers</span>
        </span>
        <span className="count">
          {attention.length} {attention.length === 1 ? "artifact" : "artifacts"}
        </span>
      </div>

      {attention.length === 0 ? (
        <div className="state" style={{ padding: "48px 0" }}>
          <div className="state__icon">✓</div>
          <h2>Nothing outstanding</h2>
          <p>Register an artifact to start building coverage.</p>
        </div>
      ) : (
        <div className="stack">
          {attention.map((a) => {
            const isOrphan = a.status === "orphan";
            return (
              <button
                key={a.artifact_id}
                type="button"
                className="row"
                onClick={() => navigate(`/artifact/${encodeURIComponent(a.artifact_id)}`)}
              >
                <span
                  className={`row__dot ${isOrphan ? "row__dot--orphan" : "row__dot--vouched"}`}
                  aria-hidden="true"
                />
                <span className="row__name">
                  <b>{basename(a.path)}</b>
                  <span>{a.path}</span>
                </span>
                {a.weak_count > 0 && (
                  <span className="pill pill--weak">{a.weak_count} weak</span>
                )}
                <span className={`pill ${isOrphan ? "pill--orphan" : "pill--vouched"}`}>
                  {a.status}
                </span>
                <span className="row__go" aria-hidden="true">
                  →
                </span>
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}

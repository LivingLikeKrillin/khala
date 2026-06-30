interface Props {
  /** grounded explanation from the server; null when the LLM call failed. */
  remediation: string | null;
  /** true when this is the last question of the session. */
  isLast: boolean;
  onAcknowledge: () => void;
}

/**
 * Calm, non-punitive review panel shown on a failed answer. Warm amber, never
 * red. Presents the grounded explanation, then "I've reviewed this" to
 * acknowledge. v0 re-queue is for the NEXT session — never re-asked here.
 */
export default function RemediationPanel({
  remediation,
  isLast,
  onAcknowledge,
}: Props) {
  return (
    <section
      className="remediation"
      role="region"
      aria-label="Let's review this"
      aria-live="polite"
    >
      <div className="remediation__head">
        <span className="icon" aria-hidden="true">
          ✦
        </span>
        <b>Let&rsquo;s review this</b>
        <span className="sub">grounded in the artifact</span>
      </div>

      {remediation ? (
        <p className="remediation__body">{remediation}</p>
      ) : (
        <p className="remediation__body remediation__none">
          No explanation was available this time — re-read the artifact section
          and we&rsquo;ll resurface this question for you next session.
        </p>
      )}

      <div className="remediation__foot">
        <span className="remediation__requeue">
          ↻ re-queued for your next session
        </span>
        <button type="button" className="btn btn--ghost" onClick={onAcknowledge}>
          {isLast ? "I've reviewed this — finish" : "I've reviewed this — next"}
        </button>
      </div>
    </section>
  );
}

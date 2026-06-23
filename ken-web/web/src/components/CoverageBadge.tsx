import type { Coverage } from "../types";

interface Props {
  coverage: Coverage;
}

/** The headline coverage dial: vouched / total with a sweeping ring. */
export default function CoverageBadge({ coverage }: Props) {
  const { covered, total, ratio } = coverage;
  const r = 33;
  const circ = 2 * Math.PI * r;
  const pct = total > 0 ? ratio : 0;
  const dash = circ * pct;
  // Amber while there's still debt to repay; sage (the vouched colour) only
  // once coverage is complete — the dial earns its green like everything else.
  const complete = total > 0 && pct >= 1;
  const ringColor = complete ? "var(--sage)" : "var(--gold)";

  return (
    <div className="coverage">
      <div className="dial">
        <svg width="76" height="76" viewBox="0 0 76 76" aria-hidden="true">
          <circle
            cx="38"
            cy="38"
            r={r}
            fill="none"
            stroke="var(--ink-700)"
            strokeWidth="5"
          />
          <circle
            cx="38"
            cy="38"
            r={r}
            fill="none"
            stroke={ringColor}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circ}`}
            style={{
              transition:
                "stroke-dasharray 0.8s cubic-bezier(.22,1,.36,1), stroke 0.5s var(--ease)",
            }}
          />
        </svg>
        <div className="dial__num">{Math.round(pct * 100)}%</div>
      </div>
      <div className="coverage__meta">
        <div className="k">Vouched</div>
        <div className="v">
          <span>{`${covered} / ${total}`}</span>{" "}
          <small>artifacts</small>
        </div>
      </div>
    </div>
  );
}

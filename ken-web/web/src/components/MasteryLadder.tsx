// 5-pip mastery ladder. Index-aligned with ken.schedule.LADDER [0,1d,3d,7d,30d];
// keep LABELS in lockstep with that ladder so a future ladder change is caught here.
const LABELS = ["due now", "1d", "3d", "7d", "30d"] as const;

export default function MasteryLadder({ rung }: { rung: number }) {
  const clamped = Math.max(0, Math.min(rung, LABELS.length - 1));
  return (
    <span className="ladder" aria-label={`mastery ${clamped} of ${LABELS.length - 1} — ${LABELS[clamped]}`}>
      {LABELS.map((_, i) => (
        <span key={i} className={`ladder__pip ${i <= clamped ? "ladder__pip--on" : ""}`} aria-hidden="true" />
      ))}
      <span className="ladder__label">{LABELS[clamped]}</span>
    </span>
  );
}

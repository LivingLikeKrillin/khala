interface Props {
  /** 1-based index of the current question. */
  current: number;
  /** total questions this session. */
  total: number;
}

/** A thin, calm progress rail + "N / M" counter. Sense of forward motion. */
export default function ProgressBar({ current, total }: Props) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return (
    <div>
      <div className="review__top">
        <span className="review__count" aria-hidden="true">
          {current} / {total}
        </span>
      </div>
      <div
        className="progress"
        role="progressbar"
        aria-valuenow={current}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={`Question ${current} of ${total}`}
      >
        <div className="progress__fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

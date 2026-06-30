import { useEffect, useRef, useState } from "react";
import type { Question } from "../types";

interface Props {
  question: Question;
  index: number; // 1-based
  total: number;
  grading: boolean;
  onSubmit: (answer: string) => void;
}

/**
 * One question, presented as prose worth thinking about. Answer textarea,
 * Submit. Cmd/Ctrl+Enter submits. Resets when the question changes so each
 * question gets a clean slate (and re-triggers the rise animation).
 */
export default function QuestionCard({
  question,
  index,
  total,
  grading,
  onSubmit,
}: Props) {
  const [answer, setAnswer] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setAnswer("");
    // focus the new question's field for uninterrupted flow
    taRef.current?.focus();
  }, [question.question_id]);

  const canSubmit = answer.trim().length > 0 && !grading;

  function submit() {
    if (!canSubmit) return;
    onSubmit(answer.trim());
  }

  return (
    <article className="qcard" key={question.question_id}>
      <div className="qcard__index">
        Question {index} of {total}
      </div>
      <h1 className="qcard__q">{question.text}</h1>

      <div className="field">
        <label htmlFor="answer" className="sr-only" style={{ position: "absolute", left: -9999 }}>
          Your answer
        </label>
        <textarea
          id="answer"
          ref={taRef}
          aria-label="Your answer"
          placeholder="Explain it in your own words — as if teaching a teammate…"
          value={answer}
          disabled={grading}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
        />
      </div>

      <div className="qactions">
        {grading ? (
          <span className="grading" aria-live="polite">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
            grading your answer
          </span>
        ) : (
          <>
            <button
              type="button"
              className="btn btn--primary btn--submit"
              disabled={!canSubmit}
              onClick={submit}
            >
              Submit answer
            </button>
            <span className="qactions__hint">
              <kbd>⌘</kbd> <kbd>↵</kbd> to submit
            </span>
          </>
        )}
      </div>
    </article>
  );
}

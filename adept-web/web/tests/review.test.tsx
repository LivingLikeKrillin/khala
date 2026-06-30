import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";

// Mock the api client BEFORE importing the component under test.
vi.mock("../src/api/client", () => ({
  getDue: vi.fn(),
  postAttempt: vi.fn(),
  getArtifacts: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import * as client from "../src/api/client";
import Review from "../src/pages/Review";

const getDue = client.getDue as unknown as ReturnType<typeof vi.fn>;
const postAttempt = client.postAttempt as unknown as ReturnType<typeof vi.fn>;
const getArtifacts = client.getArtifacts as unknown as ReturnType<typeof vi.fn>;

function renderReview(artifactId = "art-1") {
  return render(
    <MemoryRouter initialEntries={[`/review?artifact=${artifactId}`]}>
      <Routes>
        <Route path="/review" element={<Review />} />
        <Route path="/" element={<div>home stub</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Review flow (one question at a time)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getArtifacts.mockResolvedValue([
      { artifact_id: "art-1", path: "/repo/payment.md", status: "orphan", weak_count: 0 },
    ]);
    getDue.mockResolvedValue({
      questions: [
        { question_id: "q1", text: "What does the payment service publish?" },
        { question_id: "q2", text: "Who consumes the order events?" },
      ],
    });
  });

  it("advances on pass, shows remediation on fail, then ends with a summary", async () => {
    const user = userEvent.setup();
    // Q1 passes, Q2 fails with remediation.
    postAttempt
      .mockResolvedValueOnce({ passed: true, score: 0.92, remediation: null })
      .mockResolvedValueOnce({
        passed: false,
        score: 0.1,
        remediation: "The payment service publishes order events to the bus.",
      });

    renderReview();

    // First question renders, progress "1 / 2".
    expect(await screen.findByText("What does the payment service publish?")).toBeInTheDocument();
    expect(screen.getByText(/1\s*\/\s*2/)).toBeInTheDocument();

    // Answer Q1 -> pass -> auto-advance to Q2.
    await user.type(
      screen.getByRole("textbox", { name: /your answer/i }),
      "It publishes order events.",
    );
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(await screen.findByText("Who consumes the order events?")).toBeInTheDocument();
    expect(screen.getByText(/2\s*\/\s*2/)).toBeInTheDocument();
    // The pass result should not leak a remediation panel.
    expect(screen.queryByText(/let'?s review/i)).not.toBeInTheDocument();

    // Answer Q2 -> fail -> RemediationPanel with the grounded explanation.
    await user.type(
      screen.getByRole("textbox", { name: /your answer/i }),
      "the warehouse",
    );
    await user.click(screen.getByRole("button", { name: /submit/i }));

    const remediation = await screen.findByText(
      "The payment service publishes order events to the bus.",
    );
    expect(remediation).toBeInTheDocument();

    // Acknowledge -> session summary (last question, so the session ends).
    await user.click(screen.getByRole("button", { name: /reviewed/i }));

    const summary = await screen.findByRole("region", { name: /session summary/i });
    expect(summary).toBeInTheDocument();
    // 1 vouched this session, 1 queued for next session.
    expect(within(summary).getByText(/vouched this session/i)).toBeInTheDocument();
    expect(within(summary).getByText(/queued for next session/i)).toBeInTheDocument();
    // both stat counters read "1".
    const counters = within(summary)
      .getAllByText("1")
      .filter((el) => el.classList.contains("n"));
    expect(counters).toHaveLength(2);
  });

  it("calls postAttempt with the routed artifact + question ids and the answer", async () => {
    const user = userEvent.setup();
    postAttempt.mockResolvedValue({ passed: true, score: 1, remediation: null });

    // Single question so we can assert the payload cleanly.
    getDue.mockResolvedValue({
      questions: [{ question_id: "q1", text: "Only question?" }],
    });

    renderReview("art-xyz");

    await screen.findByText("Only question?");
    await user.type(screen.getByRole("textbox", { name: /your answer/i }), "my answer");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() => expect(postAttempt).toHaveBeenCalledTimes(1));
    expect(postAttempt).toHaveBeenCalledWith(
      expect.objectContaining({
        artifact_id: "art-xyz",
        question_id: "q1",
        answer: "my answer",
      }),
    );
  });

  it("shows an all-clear state when nothing is due", async () => {
    getDue.mockResolvedValue({ questions: [] });
    renderReview();
    expect(await screen.findByText(/nothing due/i)).toBeInTheDocument();
  });
});

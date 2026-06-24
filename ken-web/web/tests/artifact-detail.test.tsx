import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

// Explicit factory (matches home.test.tsx convention — mock every export used).
vi.mock("../src/api/client", () => ({
  getArtifactDetail: vi.fn(),
}));

import * as client from "../src/api/client";
import ArtifactDetail from "../src/pages/ArtifactDetail";

const getArtifactDetail = client.getArtifactDetail as unknown as ReturnType<typeof vi.fn>;

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/artifact/${id}`]}>
      <Routes>
        <Route path="/artifact/:id" element={<ArtifactDetail />} />
        <Route path="/review" element={<div>review route</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ArtifactDetail", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a row per question with overdue + never-attempted states", async () => {
    getArtifactDetail.mockResolvedValue({
      questions: [
        { question_id: "q1", text: "Q one?", rung: 0, attempted: false, last_passed: null,
          last_ts: null, fail_count: 0, next_due: null, due: true },
        { question_id: "q2", text: "Q two?", rung: 2, attempted: true, last_passed: false,
          last_ts: "2026-06-01T00:00:00Z", fail_count: 3, next_due: "2026-06-02T00:00:00+00:00", due: true },
      ],
    });
    renderAt("a1");
    expect(await screen.findByText("Q one?")).toBeInTheDocument();
    expect(screen.getByText("Q two?")).toBeInTheDocument();
    expect(screen.getByText(/overdue/i)).toBeInTheDocument();   // q2 attempted && due
    expect(screen.getByText(/3/)).toBeInTheDocument();          // fail count
  });

  it("links Start review to the artifact's review flow", async () => {
    getArtifactDetail.mockResolvedValue({ questions: [] });
    renderAt("a1");
    const cta = await screen.findByRole("link", { name: /start review/i });
    expect(cta).toHaveAttribute("href", expect.stringContaining("/review?artifact=a1"));
  });

  it("shows empty state when no questions", async () => {
    getArtifactDetail.mockResolvedValue({ questions: [] });
    renderAt("a1");
    expect(await screen.findByText(/no .*questions/i)).toBeInTheDocument();
  });
});

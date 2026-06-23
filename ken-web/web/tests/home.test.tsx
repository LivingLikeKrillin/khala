import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

vi.mock("../src/api/client", () => ({
  getArtifacts: vi.fn(),
  getCoverage: vi.fn(),
  getDue: vi.fn(),
  postAttempt: vi.fn(),
  registerArtifact: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import * as client from "../src/api/client";
import Home from "../src/pages/Home";

const getArtifacts = client.getArtifacts as unknown as ReturnType<typeof vi.fn>;
const getCoverage = client.getCoverage as unknown as ReturnType<typeof vi.fn>;

function ReviewStub() {
  const loc = useLocation();
  return <div>review route: {loc.search}</div>;
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/review" element={<ReviewStub />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Home (coverage + start review)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCoverage.mockResolvedValue({
      total: 1,
      covered: 0,
      ratio: 0,
      orphans: ["art-1"],
      weakness: [],
    });
    getArtifacts.mockResolvedValue([
      { artifact_id: "art-1", path: "/repo/payment.md", status: "orphan", weak_count: 0 },
    ]);
  });

  it("renders coverage headline and the attention list", async () => {
    renderHome();
    expect(await screen.findByText(/0\s*\/\s*1/)).toBeInTheDocument();
    expect(await screen.findByText("payment.md")).toBeInTheDocument();
  });

  it("Start review routes to /review with the first orphan", async () => {
    const user = userEvent.setup();
    renderHome();
    const cta = await screen.findByRole("button", { name: /start review/i });
    await user.click(cta);
    expect(await screen.findByText(/artifact=art-1/)).toBeInTheDocument();
  });
});

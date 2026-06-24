import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

vi.mock("../src/api/client", () => ({ getMe: vi.fn(), logout: vi.fn(), ApiError: class extends Error {} }));
import * as client from "../src/api/client";
import AuthGuard from "../src/components/AuthGuard";

const getMe = client.getMe as unknown as ReturnType<typeof vi.fn>;

function renderGuard() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<AuthGuard><div>secret content</div></AuthGuard>} />
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AuthGuard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders children when authenticated", async () => {
    getMe.mockResolvedValue({ email: "a@x.com" });
    renderGuard();
    expect(await screen.findByText("secret content")).toBeInTheDocument();
  });

  it("redirects to /login when getMe rejects (401)", async () => {
    getMe.mockRejectedValue(Object.assign(new Error("authentication required"), { status: 401 }));
    renderGuard();
    expect(await screen.findByText("login page")).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../src/api/client", () => ({ logout: vi.fn().mockResolvedValue(undefined) }));
import * as client from "../src/api/client";
import MastheadUser from "../src/components/MastheadUser";
import { AuthContext } from "../src/components/AuthGuard";

const logout = client.logout as unknown as ReturnType<typeof vi.fn>;

function renderWith(email: string) {
  return render(
    <AuthContext.Provider value={{ email }}>
      <MastheadUser />
    </AuthContext.Provider>,
  );
}

describe("MastheadUser", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the email + a Log out button when authenticated", async () => {
    renderWith("a@x.com");
    expect(screen.getByText("a@x.com")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /log ?out/i }));
    expect(logout).toHaveBeenCalled();
  });

  it("renders the static eyebrow (no logout) when auth is off (email=local)", () => {
    renderWith("local");
    expect(screen.queryByRole("button", { name: /log ?out/i })).toBeNull();
    expect(screen.getByText(/self-host/i)).toBeInTheDocument();
  });
});

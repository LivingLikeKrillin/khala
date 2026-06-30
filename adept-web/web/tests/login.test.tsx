import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

vi.mock("../src/api/client", () => ({ login: vi.fn(), ApiError: class extends Error {} }));
import * as client from "../src/api/client";
import Login from "../src/pages/Login";

const login = client.login as unknown as ReturnType<typeof vi.fn>;

function HomeStub() {
  const loc = useLocation();
  return <div>home: {loc.pathname}</div>;
}
function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<HomeStub />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits credentials and navigates home on success", async () => {
    login.mockResolvedValue({ email: "a@x.com" });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "a@x.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: /sign in|log in/i }));
    expect(login).toHaveBeenCalledWith("a@x.com", "password1");
    expect(await screen.findByText("home: /")).toBeInTheDocument();
  });

  it("shows a generic error on 401", async () => {
    login.mockRejectedValue(Object.assign(new Error("invalid email or password"), { status: 401 }));
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "a@x.com");
    await user.type(screen.getByLabelText(/password/i), "bad");
    await user.click(screen.getByRole("button", { name: /sign in|log in/i }));
    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });
});

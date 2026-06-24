import { logout } from "../api/client";
import { useAuth } from "./AuthGuard";

export default function MastheadUser() {
  const { email } = useAuth();
  if (email === "local") return <span className="eyebrow">self-host · single team</span>;
  async function doLogout() {
    await logout();
    window.location.assign("/login");
  }
  return (
    <span className="eyebrow" style={{ display: "inline-flex", gap: 12, alignItems: "center" }}>
      <span>{email}</span>
      <button type="button" className="btn btn--ghost" onClick={doLogout}>Log out</button>
    </span>
  );
}

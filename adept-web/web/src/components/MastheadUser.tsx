import { logout } from "../api/client";
import { useAuth } from "./AuthGuard";

async function doLogout() {
  try {
    await logout();
  } finally {
    window.location.assign("/login");
  }
}

export default function MastheadUser() {
  const { email } = useAuth();
  if (email === "local") return <span className="eyebrow">self-host · single team</span>;
  return (
    <span className="eyebrow" style={{ display: "inline-flex", gap: 12, alignItems: "center" }}>
      <span>{email}</span>
      <button type="button" className="btn btn--ghost" onClick={doLogout}>Log out</button>
    </span>
  );
}

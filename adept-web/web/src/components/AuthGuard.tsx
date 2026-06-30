import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getMe } from "../api/client";

interface AuthValue { email: string; }
export const AuthContext = createContext<AuthValue>({ email: "" });
export const useAuth = () => useContext(AuthContext);

type Status = "loading" | "authed" | "anon";

export default function AuthGuard({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [email, setEmail] = useState("");
  useEffect(() => {
    let alive = true;
    getMe()
      .then((m) => { if (alive) { setEmail(m.email); setStatus("authed"); } })
      .catch(() => { if (alive) setStatus("anon"); });
    return () => { alive = false; };
  }, []);
  if (status === "loading") return <div className="skeleton" style={{ height: 80, margin: 40 }} />;
  if (status === "anon") return <Navigate to="/login" replace />;
  return <AuthContext.Provider value={{ email }}>{children}</AuthContext.Provider>;
}

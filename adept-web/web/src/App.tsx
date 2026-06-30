import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Review from "./pages/Review";
import ArtifactDetail from "./pages/ArtifactDetail";
import Login from "./pages/Login";
import AuthGuard from "./components/AuthGuard";
import MastheadUser from "./components/MastheadUser";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <AuthGuard>
            <div className="shell">
              <header className="masthead">
                <Link to="/" className="wordmark">
                  <span>
                    ke<b>n</b>
                  </span>
                  <span className="tag">repayment</span>
                </Link>
                <MastheadUser />
              </header>

              <main>
                <Routes>
                  <Route path="/" element={<Home />} />
                  <Route path="/review" element={<Review />} />
                  <Route path="/artifact/:id" element={<ArtifactDetail />} />
                </Routes>
              </main>
            </div>
          </AuthGuard>
        }
      />
    </Routes>
  );
}

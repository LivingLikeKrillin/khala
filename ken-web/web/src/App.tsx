import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Review from "./pages/Review";
import ArtifactDetail from "./pages/ArtifactDetail";

export default function App() {
  return (
    <div className="shell">
      <header className="masthead">
        <Link to="/" className="wordmark">
          <span>
            ke<b>n</b>
          </span>
          <span className="tag">repayment</span>
        </Link>
        <span className="eyebrow">self-host · single team</span>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/review" element={<Review />} />
          <Route path="/artifact/:id" element={<ArtifactDetail />} />
        </Routes>
      </main>
    </div>
  );
}

import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Review from "./pages/Review";

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
        </Routes>
      </main>
    </div>
  );
}

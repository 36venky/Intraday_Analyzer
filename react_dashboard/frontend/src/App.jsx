import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Navbar from "./components/Navbar";
import GraphPage from "./pages/GraphPage";
import SignalsPage from "./pages/SignalsPage";

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#0d0d0d" }}>
        <Navbar />
        <div style={{ flex: 1, overflow: "hidden" }}>
          <Routes>
            <Route path="/"        element={<Navigate to="/graph" replace />} />
            <Route path="/graph"   element={<GraphPage />} />
            <Route path="/signals" element={<SignalsPage />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

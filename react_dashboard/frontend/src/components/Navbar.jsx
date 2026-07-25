import { NavLink } from "react-router-dom";
import { BarChart2, ClipboardList } from "lucide-react";

export default function Navbar() {
  return (
    <nav style={{
      display: "flex", alignItems: "center", gap: 0,
      background: "#0a0a0a", borderBottom: "1px solid #1e1e1e",
      padding: "0 20px", height: 48, flexShrink: 0,
    }}>
      {/* Brand */}
      <div style={{ color: "#26a69a", fontWeight: 800, fontSize: 15, marginRight: 28, letterSpacing: -0.3 }}>
        📊 Intraday Analyzer
      </div>

      {/* Nav links */}
      <NavLink to="/graph" style={({ isActive }) => navLinkStyle(isActive)}>
        <BarChart2 size={14} />
        <span>Graph</span>
      </NavLink>
      <NavLink to="/signals" style={({ isActive }) => navLinkStyle(isActive)}>
        <ClipboardList size={14} />
        <span>Signals</span>
      </NavLink>
    </nav>
  );
}

function navLinkStyle(isActive) {
  return {
    display: "flex", alignItems: "center", gap: 6, padding: "0 16px",
    height: 48, fontSize: 13, textDecoration: "none",
    color: isActive ? "#26a69a" : "#666",
    borderBottom: isActive ? "2px solid #26a69a" : "2px solid transparent",
    transition: "color 0.15s, border-color 0.15s",
    fontWeight: isActive ? 600 : 400,
  };
}

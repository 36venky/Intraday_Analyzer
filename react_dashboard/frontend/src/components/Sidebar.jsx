import { BarChart2, Activity, TrendingUp, TrendingDown, Layers, Minus, AlignCenter, Maximize2 } from "lucide-react";

const Toggle = ({ label, icon: Icon, checked, onChange, color }) => (
  <label style={{
    display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
    cursor: "pointer", borderRadius: 6, transition: "background 0.15s",
    background: checked ? "rgba(255,255,255,0.06)" : "transparent",
    userSelect: "none",
  }}
    onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.05)"}
    onMouseLeave={e => e.currentTarget.style.background = checked ? "rgba(255,255,255,0.06)" : "transparent"}
  >
    <div style={{
      width: 32, height: 18, borderRadius: 9,
      background: checked ? (color || "#26a69a") : "#333",
      position: "relative", transition: "background 0.2s", flexShrink: 0,
    }}
      onClick={onChange}
    >
      <div style={{
        position: "absolute", top: 3, left: checked ? 16 : 3,
        width: 12, height: 12, borderRadius: "50%", background: "#fff",
        transition: "left 0.2s",
      }} />
    </div>
    {Icon && <Icon size={13} color={checked ? (color || "#26a69a") : "#555"} />}
    <span style={{ fontSize: 12, color: checked ? "#ccc" : "#666" }}>{label}</span>
  </label>
);

const Section = ({ title, children }) => (
  <div style={{ marginBottom: 16 }}>
    <div style={{ fontSize: 10, color: "#444", fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, padding: "0 10px 6px" }}>
      {title}
    </div>
    {children}
  </div>
);

export default function Sidebar({ settings, onChange }) {
  const set = (key, val) => onChange({ ...settings, [key]: val });
  const tog = key => () => set(key, !settings[key]);

  return (
    <div style={{
      width: 200, background: "#111", borderRight: "1px solid #222",
      height: "100vh", overflowY: "auto", padding: "16px 0", flexShrink: 0,
      position: "sticky", top: 0,
    }}>
      <div style={{ padding: "0 10px 16px", borderBottom: "1px solid #1e1e1e", marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#e0e0e0" }}>📊 Indicators</div>
      </div>

      <Section title="Chart">
        <Toggle label="Line Chart"   icon={Activity}   checked={settings.showLine}  onChange={tog("showLine")} />
      </Section>

      <Section title="Overlays">
        <Toggle label="EMA 9 / 21"   icon={TrendingUp}  checked={settings.showEma}         onChange={tog("showEma")}   color="#ffd54f" />
        <Toggle label="VWAP"          icon={AlignCenter} checked={settings.showVwap}        onChange={tog("showVwap")}  color="#80cbc4" />
        <Toggle label="PDH / PDL"     icon={Maximize2}   checked={settings.showPdhPdl}      onChange={tog("showPdhPdl")} color="#ffb74d" />
      </Section>

      <Section title="Structure">
        <Toggle label="Swing H/L"    icon={Activity}    checked={settings.showSwings}       onChange={tog("showSwings")} />
        <Toggle label="Swing Zones"  icon={Layers}      checked={settings.showSwingZones}   onChange={tog("showSwingZones")} />
        <Toggle label="Supports"     icon={TrendingUp}  checked={settings.showSupports}     onChange={tog("showSupports")}  color="#26a69a" />
        <Toggle label="Resistance"   icon={TrendingDown} checked={settings.showResistance}  onChange={tog("showResistance")} color="#ef5350" />
        <Toggle label="Trendlines"   icon={Minus}       checked={settings.showTrendlines}   onChange={tog("showTrendlines")} />
        <Toggle label="FVG"          icon={BarChart2}   checked={settings.showFvg}          onChange={tog("showFvg")}   color="#ce93d8" />
      </Section>

      <Section title="Sub-Charts">
        <Toggle label="RSI (14)"     icon={Activity}    checked={settings.showRsi}          onChange={tog("showRsi")}   color="#64b5f6" />
      </Section>
    </div>
  );
}

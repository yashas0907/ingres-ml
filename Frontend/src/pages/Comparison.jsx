import { useState } from "react";
import { Bar, Radar } from "react-chartjs-2";
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend
} from "chart.js";
import { API_BASE } from "../utils/api";
import ExportMenu from "../components/ExportMenu";
import { exportComparisonPDF, exportComparisonCSV } from "../utils/exportUtils";

ChartJS.register(
  CategoryScale, LinearScale, BarElement,
  RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend
);

const STATES = [
  "Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi", "Gujarat",
  "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab", "Rajasthan",
  "Tamil Nadu", "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal",
];

const CATEGORY_COLORS = {
  "Safe": "#2ecc71", "Semi-Critical": "#f39c12",
  "Critical": "#e67e22", "Over-Exploited": "#e74c3c",
};

export default function Comparison() {
  const [locations, setLocations] = useState(["Punjab", "Haryana", "Bihar"]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [chartType, setChartType] = useState("bar");

  const addLocation = () => setLocations(l => [...l, ""]);
  const removeLocation = (i) => setLocations(l => l.filter((_, idx) => idx !== i));
  const updateLocation = (i, val) => setLocations(l => l.map((x, idx) => idx === i ? val : x));

  const compare = async () => {
    setLoading(true);
    setResults([]);
    try {
      const res = await fetch(`${API_BASE}/api/ml/compare-districts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locations: locations.filter(Boolean) }),
      });
      const data = await res.json();
      setResults(data.comparison || []);
    } catch { }
    setLoading(false);
  };

  const barChartData = {
    labels: results.map(r => r.name),
    datasets: [{
      label: "Extraction (%)",
      data: results.map(r => r.extraction),
      backgroundColor: results.map(r => r.color || "#888"),
      borderRadius: 8,
      borderSkipped: false,
    }, {
      label: "Est. Recharge (rel.)",
      data: results.map(r => r.recharge_estimate),
      backgroundColor: results.map(() => "rgba(0,163,224,0.4)"),
      borderRadius: 8,
      borderSkipped: false,
    }]
  };

  const radarData = results.length > 0 ? {
    labels: ["Extraction %", "Est. Recharge", "Risk Score"],
    datasets: results.map((r) => ({
      label: r.name,
      data: [
        Math.min(r.extraction, 200),
        Math.min(r.recharge_estimate, 200),
        r.category === "Over-Exploited" ? 100 :
        r.category === "Critical" ? 75 :
        r.category === "Semi-Critical" ? 50 : 25,
      ],
      borderColor: r.color,
      backgroundColor: r.color + "33",
      pointBackgroundColor: r.color,
    }))
  } : null;

  const exportOptions = results.length > 0 ? [
    {
      id: "pdf",
      type: "pdf",
      label: "Comparison Report (with chart)",
      action: () => exportComparisonPDF({
        results,
        chartSelector: "#comparison-chart-capture",
      }),
    },
    {
      id: "csv",
      type: "csv",
      label: "Comparison Data",
      action: () => exportComparisonCSV(results),
    },
  ] : [];

  return (
    <div className="page-content comparison-page">
      <div className="page-header-row">
        <div>
          <h1>District Comparison</h1>
          <p>Compare groundwater status between states and districts side-by-side</p>
        </div>
        {results.length > 0 && <ExportMenu options={exportOptions} />}
      </div>

      <div className="comparison-form">
        <h3>Select Locations to Compare</h3>
        <div className="location-inputs">
          {locations.map((loc, i) => (
            <div key={i} className="location-row">
              <select value={loc} onChange={e => updateLocation(i, e.target.value)}>
                <option value="">-- Select State --</option>
                {STATES.map(s => <option key={s}>{s}</option>)}
              </select>
              {locations.length > 2 && (
                <button className="remove-btn" onClick={() => removeLocation(i)}>✕</button>
              )}
            </div>
          ))}
        </div>
        <div className="form-actions">
          {locations.length < 6 && (
            <button className="add-btn" onClick={addLocation}>+ Add Location</button>
          )}
          <button className="pred-btn" onClick={compare} disabled={loading || locations.filter(Boolean).length < 2}>
            {loading ? <span className="btn-loader"></span> : "Compare"}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <>
          <div className="comparison-cards">
            {results.map((r, i) => (
              <div key={i} className="comparison-card" style={{ borderTopColor: r.color }}>
                <h4>{r.name}</h4>
                <div className="cc-extraction" style={{ color: r.color }}>{r.extraction}%</div>
                <div className="cc-label">Extraction Rate</div>
                <div className="cc-badge" style={{ background: r.color + "22", color: r.color }}>
                  {r.category}
                </div>
                <div className="cc-bar-bg">
                  <div className="cc-bar-fill" style={{
                    width: `${Math.min(r.extraction, 200) / 2}%`,
                    background: r.color
                  }}></div>
                </div>
                <div className="cc-recharge">Est. Recharge: {r.recharge_estimate}%</div>
              </div>
            ))}
          </div>

          <div className="chart-type-tabs">
            <button className={chartType === "bar" ? "active" : ""} onClick={() => setChartType("bar")}>Bar Chart</button>
            <button className={chartType === "radar" ? "active" : ""} onClick={() => setChartType("radar")}>Radar Chart</button>
          </div>

          <div id="comparison-chart-capture" className="chart-panel" style={{ height: 350 }}>
            {chartType === "bar" ? (
              <Bar data={barChartData} options={{
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: {
                  y: { ticks: { callback: v => `${v}%` }, grid: { color: "rgba(0,0,0,0.05)" } },
                  x: { grid: { display: false } }
                }
              }} />
            ) : radarData ? (
              <Radar data={radarData} options={{
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: { r: { min: 0, max: 200, ticks: { display: false } } }
              }} />
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

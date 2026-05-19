import { useState, useEffect } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, Tooltip, Legend, Filler
} from "chart.js";
import { API_BASE } from "../utils/api";
import ExportMenu from "../components/ExportMenu";
import { exportTrendsPDF, exportTrendsCSV } from "../utils/exportUtils";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

const PALETTE = [
  "#e74c3c","#00A3E0","#2ecc71","#f39c12","#9b59b6","#1abc9c",
  "#e67e22","#3498db","#e91e63","#4caf50","#ff5722","#607d8b",
];

export default function TrendAnalysis() {
  const [trends, setTrends] = useState([]);
  const [years, setYears] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    fetch(`${API_BASE}/api/ml/trend-analysis`)
      .then(r => r.json())
      .then(data => {
        const t = data.trends || [];
        setTrends(t);
        setYears(data.years || []);
        setSelected(t.slice(0, 6).map(s => s.state));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const filteredTrends = trends.filter(t => {
    if (filter === "all") return true;
    return t.category?.toLowerCase() === filter.toLowerCase();
  });

  const toggleState = (state) => {
    setSelected(prev =>
      prev.includes(state) ? prev.filter(s => s !== state) : [...prev, state]
    );
  };

  const chartData = {
    labels: years,
    datasets: selected.map((stateName, i) => {
      const t = trends.find(x => x.state === stateName);
      if (!t) return null;
      return {
        label: stateName.charAt(0).toUpperCase() + stateName.slice(1),
        data: years.map(y => {
          const v = t.values.find(x => x.year === y);
          return v ? v.extraction : null;
        }),
        borderColor: PALETTE[i % PALETTE.length],
        backgroundColor: "transparent",
        tension: 0.4,
        pointRadius: 5,
        pointHoverRadius: 7,
        borderWidth: 2,
      };
    }).filter(Boolean),
  };

  const exportOptions = [
    {
      id: "pdf",
      type: "pdf",
      label: "Trend Analysis Report (PDF)",
      action: () => exportTrendsPDF({ trends: filteredTrends, years, selectedStates: selected }),
    },
    {
      id: "csv-all",
      type: "csv",
      label: "All States — Trend Data",
      action: () => exportTrendsCSV(trends, years),
    },
    {
      id: "csv-filtered",
      type: "csv",
      label: "Selected States Only",
      action: () => exportTrendsCSV(trends.filter(t => selected.includes(t.state)), years),
    },
  ];

  if (loading) return (
    <div className="page-loading">
      <div className="water-loader"></div>
      <p>Loading trend data…</p>
    </div>
  );

  return (
    <div className="page-content trends-page">
      <div className="page-header-row">
        <div>
          <h1>Trend Analysis</h1>
          <p>Historical groundwater extraction trends across Indian states (2017–2022)</p>
        </div>
        <ExportMenu options={exportOptions} loading={loading} />
      </div>

      <div className="trend-controls">
        <div className="filter-tabs">
          {["all", "Over-Exploited", "Critical", "Semi-Critical", "Safe"].map(f => (
            <button
              key={f}
              className={`filter-tab ${filter === f ? "active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All States" : f}
            </button>
          ))}
        </div>
      </div>

      <div className="trend-layout">
        <div className="state-selector">
          <h4>Select States ({selected.length} selected)</h4>
          <div className="state-list">
            {filteredTrends.map((t, i) => {
              const isSelected = selected.includes(t.state);
              const colorIdx = selected.indexOf(t.state);
              return (
                <div
                  key={t.state}
                  className={`state-item ${isSelected ? "selected" : ""}`}
                  onClick={() => toggleState(t.state)}
                  style={isSelected ? { borderLeftColor: PALETTE[colorIdx % PALETTE.length] } : {}}
                >
                  <span className="state-name">
                    {t.state.charAt(0).toUpperCase() + t.state.slice(1)}
                  </span>
                  <div className="state-meta">
                    <span
                      className="state-cat-badge"
                      style={{ background: (t.color || "#888") + "22", color: t.color || "#888" }}
                    >
                      {t.category}
                    </span>
                    <span className="state-extr">{t.latest_extraction}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="trend-chart-area">
          <div id="trend-chart-capture" className="chart-panel" style={{ height: 420 }}>
            {selected.length > 0 ? (
              <Line data={chartData} options={{
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                  legend: { position: "top", labels: { padding: 16, font: { size: 12 } } },
                  tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.raw}%` } }
                },
                scales: {
                  y: {
                    ticks: { callback: v => `${v}%` },
                    grid: { color: "rgba(0,0,0,0.05)" },
                    title: { display: true, text: "Extraction (%)" }
                  },
                  x: {
                    grid: { display: false },
                    title: { display: true, text: "Year" }
                  }
                }
              }} />
            ) : (
              <div className="empty-chart">Select states from the left panel to view trends</div>
            )}
          </div>

          <div className="trend-table">
            <table>
              <thead>
                <tr>
                  <th>State</th>
                  {years.map(y => <th key={y}>{y}</th>)}
                  <th>Category</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrends.map(t => (
                  <tr key={t.state} className={selected.includes(t.state) ? "highlighted-row" : ""}>
                    <td>{t.state.charAt(0).toUpperCase() + t.state.slice(1)}</td>
                    {years.map(y => {
                      const v = t.values.find(x => x.year === y);
                      return (
                        <td key={y} style={{
                          color: v && v.extraction > 100 ? "#e74c3c" :
                                 v && v.extraction > 90 ? "#e67e22" :
                                 v && v.extraction > 70 ? "#f39c12" : "#2ecc71"
                        }}>
                          {v ? `${v.extraction}%` : "—"}
                        </td>
                      );
                    })}
                    <td>
                      <span className="state-cat-badge" style={{ background: (t.color || "#888") + "22", color: t.color || "#888" }}>
                        {t.category}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

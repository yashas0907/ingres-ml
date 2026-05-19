import { useState, useEffect } from "react";
import { Doughnut, Bar } from "react-chartjs-2";
import {
  Chart as ChartJS, ArcElement, CategoryScale, LinearScale,
  BarElement, Tooltip, Legend
} from "chart.js";
import { API_BASE } from "../utils/api";
import ExportMenu from "../components/ExportMenu";
import {
  exportDashboardPDF,
  exportDashboardCSV,
} from "../utils/exportUtils";

ChartJS.register(ArcElement, CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const CATEGORY_COLORS = {
  "Safe": "#2ecc71",
  "Semi-Critical": "#f39c12",
  "Critical": "#e67e22",
  "Over-Exploited": "#e74c3c",
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [distribution, setDistribution] = useState([]);
  const [topRisk, setTopRisk] = useState([]);
  const [modelStats, setModelStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/ml/overview-stats`).then(r => r.json()),
      fetch(`${API_BASE}/api/ml/district-distribution`).then(r => r.json()),
      fetch(`${API_BASE}/api/ml/top-risk-districts?limit=10`).then(r => r.json()),
      fetch(`${API_BASE}/api/ml/model-stats`).then(r => r.json()),
    ]).then(([s, d, t, m]) => {
      setStats(s);
      setDistribution(d.distribution || []);
      setTopRisk(t.districts || []);
      setModelStats(m);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="page-loading">
      <div className="water-loader"></div>
      <p>Loading dashboard data…</p>
    </div>
  );

  const donutData = {
    labels: distribution.map(d => d.category),
    datasets: [{
      data: distribution.map(d => d.count),
      backgroundColor: distribution.map(d => CATEGORY_COLORS[d.category] || "#888"),
      borderColor: "#fff",
      borderWidth: 2,
    }]
  };

  const barData = {
    labels: topRisk.map(d => d.district?.substring(0, 12) || d.state?.substring(0, 12)),
    datasets: [{
      label: "Extraction (%)",
      data: topRisk.map(d => d.extraction),
      backgroundColor: topRisk.map(d => d.color || "#e74c3c"),
      borderRadius: 6,
      borderSkipped: false,
    }]
  };

  const exportOptions = [
    {
      id: "pdf",
      type: "pdf",
      label: "Full Dashboard Report",
      action: () => exportDashboardPDF({ stats, distribution, topRisk, modelStats }),
    },
    {
      id: "csv",
      type: "csv",
      label: "Overview Stats & Districts",
      action: () => exportDashboardCSV(stats, distribution, topRisk),
    },
  ];

  return (
    <div className="page-content dashboard-page">
      <div className="page-header-row">
        <div>
          <h1>INGRES Dashboard</h1>
          <p>AI + ML powered groundwater analysis across India</p>
        </div>
        <ExportMenu options={exportOptions} loading={loading} />
      </div>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{stats.total_blocks?.toLocaleString()}</div>
            <div className="stat-label">Total Blocks Assessed</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.total_states}</div>
            <div className="stat-label">States Covered</div>
          </div>
          <div className="stat-card danger">
            <div className="stat-value">{stats.over_exploited_blocks?.toLocaleString()}</div>
            <div className="stat-label">Over-Exploited Blocks</div>
            <div className="stat-sub">{stats.over_exploited_pct}% of total</div>
          </div>
          <div className="stat-card safe">
            <div className="stat-value">{stats.safe_blocks?.toLocaleString()}</div>
            <div className="stat-label">Safe Blocks</div>
          </div>
          <div className="stat-card warning">
            <div className="stat-value">{stats.avg_extraction}%</div>
            <div className="stat-label">Avg. Extraction Rate</div>
          </div>
        </div>
      )}

      <div className="charts-row">
        <div className="chart-panel">
          <h3>Category Distribution</h3>
          <div style={{ height: 280 }}>
            <Doughnut data={donutData} options={{
              responsive: true, maintainAspectRatio: false,
              plugins: {
                legend: { position: "bottom", labels: { padding: 16, font: { size: 12 } } },
                tooltip: {
                  callbacks: {
                    label: (ctx) => {
                      const d = distribution[ctx.dataIndex];
                      return ` ${d?.count} blocks (${d?.percentage}%)`;
                    }
                  }
                }
              }
            }} />
          </div>
        </div>

        <div className="chart-panel">
          <h3>Top 10 Most Stressed Districts</h3>
          <div style={{ height: 280 }}>
            <Bar data={barData} options={{
              responsive: true, maintainAspectRatio: false,
              indexAxis: "y",
              plugins: { legend: { display: false } },
              scales: {
                x: {
                  beginAtZero: true,
                  ticks: { callback: v => `${v}%` },
                  grid: { color: "rgba(0,0,0,0.05)" }
                },
                y: { grid: { display: false } }
              }
            }} />
          </div>
        </div>
      </div>

      {modelStats && (
        <div className="model-stats-panel">
          <h3>ML Model Performance</h3>
          <div className="model-stats-grid">
            <div className="model-block">
              <h4>Risk Classifiers</h4>
              <div className="model-rows">
                {["svm", "random_forest", "decision_tree"].map(k => (
                  <div key={k} className={`model-row ${modelStats.classifiers?.best_model === k ? "best" : ""}`}>
                    <span className="model-name">
                      {k === "svm" ? "SVM" : k === "random_forest" ? "Random Forest" : "Decision Tree"}
                      {modelStats.classifiers?.best_model === k && <span className="best-badge">Best</span>}
                    </span>
                    <span className="model-metric">
                      Accuracy: <strong>{modelStats.classifiers?.[k]?.accuracy}%</strong>
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="model-block">
              <h4>Extraction Regressors</h4>
              <div className="model-rows">
                {["linear_regression", "random_forest"].map(k => (
                  <div key={k} className={`model-row ${modelStats.regressors?.best_model === k ? "best" : ""}`}>
                    <span className="model-name">
                      {k === "linear_regression" ? "Linear Regression" : "Random Forest"}
                      {modelStats.regressors?.best_model === k && <span className="best-badge">Best</span>}
                    </span>
                    <span className="model-metric">
                      RMSE: <strong>{modelStats.regressors?.[k]?.rmse}</strong>
                      &nbsp;|&nbsp;R²: <strong>{modelStats.regressors?.[k]?.r2}</strong>
                    </span>
                  </div>
                ))}
              </div>
            </div>
            {modelStats.classifiers?.feature_importances && (
              <div className="model-block">
                <h4>Feature Importance (RF Classifier)</h4>
                <div className="importance-bars">
                  {Object.entries(modelStats.classifiers.feature_importances).map(([feat, val]) => (
                    <div key={feat} className="importance-row">
                      <span className="imp-label">{feat.replace(/_/g, " ")}</span>
                      <div className="imp-bar-bg">
                        <div className="imp-bar-fill" style={{ width: `${val}%` }}></div>
                      </div>
                      <span className="imp-val">{val}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

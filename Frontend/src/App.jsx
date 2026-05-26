import { useState, useRef, useEffect } from "react";
import GroundwaterMap from "./GroundwaterMap";
import WebGLWaves from "./components/WebGLWaves";
import MapLegend from "./components/MapLegend";
import Dashboard from "./pages/Dashboard";
import Predictions from "./pages/Predictions";
import TrendAnalysis from "./pages/TrendAnalysis";
import Comparison from "./pages/Comparison";
import { Bar, Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend
} from "chart.js";
import "./App.css";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend);

const TABS = [
  { id: "chat", label: "💬 Chat", icon: "💬" },
  { id: "dashboard", label: "📊 Dashboard", icon: "📊" },
  { id: "predict", label: "🎯 Predictions", icon: "🎯" },
  { id: "trends", label: "📈 Trends", icon: "📈" },
  { id: "compare", label: "⚖️ Compare", icon: "⚖️" },
  { id: "map", label: "🗺️ India Map", icon: "🗺️" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("chat");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [displayedMain, setDisplayedMain] = useState("");
  const [displayedSuffix, setDisplayedSuffix] = useState("");
  const [isRetreating, setIsRetreating] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const mainText = "INGRES";
    const suffixText = " — AI Groundwater Intelligence System";
    let i = 0;
    let typeSuffixInterval;
    const typeMainInterval = setInterval(() => {
      if (i < mainText.length) {
        setDisplayedMain(mainText.slice(0, i + 1));
        i++;
      } else {
        clearInterval(typeMainInterval);
        let j = 0;
        typeSuffixInterval = setInterval(() => {
          if (j < suffixText.length) {
            setDisplayedSuffix(suffixText.slice(0, j + 1));
            j++;
          } else {
            clearInterval(typeSuffixInterval);
            setTimeout(() => setIsRetreating(true), 2000);
          }
        }, 35);
      }
    }, 60);
    return () => { clearInterval(typeMainInterval); clearInterval(typeSuffixInterval); };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const API_BASE =
    window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? "http://localhost:8000"
      : "";

  const sendMessage = async (explicitMsg = null) => {
    const userMsg = typeof explicitMsg === "string" ? explicitMsg : input;
    if (!userMsg.trim()) return;

    if (userMsg.toLowerCase().includes("show india map")) {
      setActiveTab("map");
      return;
    }
    if (userMsg.toLowerCase().includes("show dashboard")) {
      setActiveTab("dashboard");
      return;
    }
    if (userMsg.toLowerCase().includes("predict") && !userMsg.toLowerCase().includes("?")) {
      setActiveTab("predict");
      return;
    }

    setMessages((m) => [...m, { type: "user", text: userMsg }]);
    setInput("");
    setLoading(true);

    // Timeout safety: abort fetch after 45 seconds
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    try {
      const response = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, stream: true }),
        signal: controller.signal
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      setMessages((m) => [
        ...m,
        { type: "bot", text: "", chartData: [], visualType: null, visualData: null, imageUrl: null, showLegend: false, suggestions: [] }
      ]);

      let accumulatedText = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop();

        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(part.substring(6));
            if (data.t) {
              accumulatedText += data.t;
              setMessages((m) => {
                const nm = [...m];
                nm[nm.length - 1].text = accumulatedText;
                return nm;
              });
            } else if (data.m) {
              setMessages((m) => {
                const nm = [...m];
                const last = nm[nm.length - 1];
                last.chartData = data.m.chartData || [];
                last.visualType = data.m.visualType || null;
                last.visualData = data.m.visualData || null;
                last.imageUrl = data.m.imageUrl || null;
                last.showLegend = data.m.showLegend || false;
                last.suggestions = data.m.suggestions || [];
                return nm;
              });
            }
          } catch (e) { console.error("Stream parse error", e); }
        }
      }

      // Safety: if stream ended but no text was received, show fallback
      if (!accumulatedText.trim()) {
        setMessages((m) => {
          const nm = [...m];
          nm[nm.length - 1].text = "I couldn't process that request. Please try asking something else.";
          nm[nm.length - 1].suggestions = ["What is groundwater?", "Conservation tips", "Show India map"];
          return nm;
        });
      }
    } catch (err) {
      const isTimeout = err.name === "AbortError";
      setMessages((m) => [
        ...m,
        {
          type: "bot",
          text: isTimeout
            ? "The request took too long. Please try again with a simpler question."
            : "Backend not responding. Please check your connection.",
          suggestions: ["What is groundwater?", "Conservation tips", "Compare Punjab and Bihar"]
        }
      ]);
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const formatText = (text) => {
    if (!text) return "";
    let html = text
      // Headings: ### Title
      .replace(/###\s*(.*?)(?:\n|$)/g, '<div class="bot-heading">$1</div>')
      // Bold: **text**
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      // Bullet points: • item or * item or - item (at start of line)
      .replace(/^[•\*\-]\s+(.+)$/gm, '<li>$1</li>')
      // Wrap consecutive <li> in <ul>
      .replace(/(<li>.*?<\/li>\n?)+/gs, (match) => `<ul class="bot-list">${match}</ul>`)
      // Line breaks
      .replace(/\n/g, '<br/>');
    return html;
  };

  return (
    <div className="app">
      <WebGLWaves />
      <header className="header">
        <div className="header-title">
          <span className="brand-main">{displayedMain}</span>
          <span className={`brand-suffix ${isRetreating ? "retreat" : ""}`}>{displayedSuffix}</span>
        </div>
        <nav className="tab-nav">
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="main-content">
        {activeTab === "dashboard" && <Dashboard />}
        {activeTab === "predict" && <Predictions />}
        {activeTab === "trends" && <TrendAnalysis />}
        {activeTab === "compare" && <Comparison />}
        {activeTab === "map" && (
          <div className="map-view"><GroundwaterMap /></div>
        )}

        {activeTab === "chat" && (
          <div className="chat">
            {messages.length === 0 && (
              <div className="welcome-container">
                <div className="welcome-box">
                  <h2>INGRES AI Assistant</h2>
                  <p>
                    AI + ML powered groundwater intelligence for India.
                    Ask me anything about groundwater, districts, or use the tabs above for ML predictions.
                  </p>
                  <div className="suggestions-box">
                    <p><b>Try asking me:</b></p>
                    <div className="suggestions-list">
                      {[
                        "Compare Punjab and Bihar",
                        "Why is Rajasthan stressed?",
                        "Which districts are over-exploited?",
                        "Check water quality in Gujarat",
                        "Show groundwater trends",
                      ].map((s, i) => (
                        <button key={i} className="suggestion-btn" onClick={() => sendMessage(s)}>{s}</button>
                      ))}
                      <button className="suggestion-btn highlight" onClick={() => setActiveTab("dashboard")}>
                        Open ML Dashboard
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.type} msg-animate`}>
                {m.type === "bot" && <div className="bot-avatar">🌊</div>}
                <div className="bubble">
                  {m.type === "bot"
                    ? <div className="bot-text-content" dangerouslySetInnerHTML={{ __html: formatText(m.text) }} />
                    : m.text
                  }
                </div>

                {m.type === "bot" && m.imageUrl && (
                  <div className="bot-image-container">
                    <img src={m.imageUrl} alt="Groundwater visual" className="bot-image" />
                    {m.showLegend && <div className="chat-legend-wrapper"><MapLegend /></div>}
                  </div>
                )}

                {m.visualType === "status_card" && m.visualData && (
                  <div className="status-card">
                    <div className="status-header">
                      <h3>{m.visualData.name}</h3>
                      <span className={`category-badge ${m.visualData.category.toLowerCase().replace(" ", "-")}`}>
                        {m.visualData.category}
                      </span>
                    </div>
                    <div className="status-grid">
                      <div className="status-item"><label>Extraction</label><span>{m.visualData.extraction}%</span></div>
                      <div className="status-item"><label>Trend</label><span>{m.visualData.trend}</span></div>
                    </div>
                    <div className="status-info">
                      <p><strong>Cause:</strong> {m.visualData.mainCause}</p>
                      <p><strong>Risk:</strong> {m.visualData.topRisk}</p>
                    </div>
                    <div className="status-action">
                      <strong>Action:</strong> {m.visualData.recommendedAction}
                    </div>
                  </div>
                )}

                {m.visualType === "comparison_bars" && m.visualData && (
                  <div className="comparison-container">
                    <h3>Regional Comparison</h3>
                    <div className="comparison-bars-list">
                      {m.visualData.map((d, di) => (
                        <div key={di} className="comparison-bar-row">
                          <div className="bar-label">{d.name}</div>
                          <div className="bar-wrapper">
                            <div className={`bar-fill ${d.category.toLowerCase().replace(" ", "-")}`}
                              style={{ width: `${Math.min(d.extraction, 100)}%` }}></div>
                            <span className="bar-value">{d.extraction}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {m.visualType === "risk_alert" && m.visualData && (
                  <div className="risk-alert-card">
                    <div className="alert-header">
                      <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" strokeWidth="2" fill="none">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                        <line x1="12" y1="9" x2="12" y2="13"></line>
                        <line x1="12" y1="17" x2="12.01" y2="17"></line>
                      </svg>
                      <h4>Water Quality Alert</h4>
                    </div>
                    <div className="alert-content">
                      <p><strong>Contaminants:</strong> {m.visualData.contaminantList.join(", ")}</p>
                      <p>{m.visualData.healthRisk}</p>
                    </div>
                    <div className="alert-footer">
                      <strong>Mitigation:</strong> {m.visualData.suggestedMitigation}
                    </div>
                  </div>
                )}

                {m.visualType === "trend_line" && m.visualData && (
                  <div className="chart-card trend-card">
                    <h3>{m.visualData.name} Extraction Trend</h3>
                    <div className="chart-container">
                      <Line data={{
                        labels: m.visualData.labels,
                        datasets: [{
                          label: "Extraction (%)", data: m.visualData.values, fill: false,
                          borderColor: "#011627", backgroundColor: "#011627", tension: 0.3,
                          pointRadius: 6, pointHoverRadius: 8
                        }]
                      }} options={{
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: { y: { beginAtZero: false, ticks: { callback: (v) => `${v}%` } } }
                      }} />
                    </div>
                    <div className={`trend-diagnostic ${m.visualData.diagnostic}`}>
                      Status: {m.visualData.diagnostic.charAt(0).toUpperCase() + m.visualData.diagnostic.slice(1)}
                    </div>
                  </div>
                )}

                {m.type === "bot" && m.suggestions?.length > 0 && (
                  <div className="bot-suggestions">
                    {m.suggestions.map((s, si) => (
                      <button key={si} className="suggestion-btn small" onClick={() => sendMessage(s)}>{s}</button>
                    ))}
                  </div>
                )}

                {m.chartData?.length > 0 && (
                  <div className="chart-card">
                    <div className="chart-container">
                      <Bar data={{
                        labels: m.chartData.map((d) => d.name),
                        datasets: [{
                          label: "Extraction (%)",
                          data: m.chartData.map((d) => d.extraction),
                          backgroundColor: m.chartData.map((d) =>
                            d.extraction <= 70 ? "rgba(46,204,113,0.85)" : d.extraction <= 100 ? "rgba(241,196,15,0.85)" : "rgba(231,76,60,0.85)"
                          ),
                          borderColor: m.chartData.map((d) =>
                            d.extraction <= 70 ? "#27ae60" : d.extraction <= 100 ? "#f39c12" : "#c0392b"
                          ),
                          borderWidth: 1, borderRadius: 8
                        }]
                      }} options={{
                        responsive: true, maintainAspectRatio: false,
                        animation: { duration: 2000, easing: "easeOutQuart" },
                        plugins: { legend: { display: false } },
                        scales: {
                          y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.05)" }, ticks: { callback: (v) => `${v}%` } },
                          x: { grid: { display: false } }
                        }
                      }} />
                    </div>
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="msg bot msg-animate">
                <div className="bot-avatar">🌊</div>
                <div className="bubble">
                  <div className="typing-indicator">
                    <div className="typing-dots">
                      <span></span><span></span><span></span>
                    </div>
                    <span className="loading-text">INGRES is thinking…</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {activeTab === "chat" && (
        <div className="input-box">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about India's groundwater…"
            aria-label="Chat message input"
          />
          <button className="send-btn" onClick={sendMessage} disabled={loading} aria-label="Send">
            {loading ? <span className="btn-loader"></span> : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5"></line>
                <polyline points="5 12 12 5 19 12"></polyline>
              </svg>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

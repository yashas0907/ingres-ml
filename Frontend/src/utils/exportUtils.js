import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import html2canvas from "html2canvas";

const BRAND_DARK = [1, 22, 39];
const BRAND_BLUE = [0, 163, 224];
const BRAND_LIGHT = [240, 248, 255];
const SAFE_COLOR = [46, 204, 113];
const WARN_COLOR = [243, 156, 18];
const CRIT_COLOR = [230, 126, 34];
const DANGER_COLOR = [231, 76, 60];

const CATEGORY_RGB = {
  "Safe":          SAFE_COLOR,
  "Semi-Critical": WARN_COLOR,
  "Critical":      CRIT_COLOR,
  "Over-Exploited": DANGER_COLOR,
};

function getCategoryRgb(cat) {
  return CATEGORY_RGB[cat] || [136, 136, 136];
}

function timestamp() {
  return new Date().toLocaleString("en-IN", {
    dateStyle: "long", timeStyle: "short", timeZone: "Asia/Kolkata"
  });
}

function reportId() {
  return "INGRES-" + Date.now().toString(36).toUpperCase();
}

function addHeader(doc, title, subtitle = "") {
  const W = doc.internal.pageSize.getWidth();

  doc.setFillColor(...BRAND_DARK);
  doc.rect(0, 0, W, 28, "F");

  doc.setFillColor(...BRAND_BLUE);
  doc.rect(0, 26, W, 3, "F");

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(16);
  doc.setFont("helvetica", "bold");
  doc.text("INGRES", 14, 12);

  doc.setFontSize(8);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(122, 215, 240);
  doc.text("AI + ML Powered Groundwater Intelligence System", 14, 20);

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.text(title, W - 14, 12, { align: "right" });

  if (subtitle) {
    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(186, 233, 247);
    doc.text(subtitle, W - 14, 20, { align: "right" });
  }

  return 36;
}

function addMetaRow(doc, y, rid) {
  const W = doc.internal.pageSize.getWidth();
  doc.setFillColor(...BRAND_LIGHT);
  doc.rect(0, y, W, 12, "F");
  doc.setFontSize(7.5);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(100, 116, 139);
  doc.text(`Generated: ${timestamp()}`, 14, y + 8);
  doc.text(`Report ID: ${rid}`, W - 14, y + 8, { align: "right" });
  doc.setDrawColor(209, 233, 255);
  doc.setLineWidth(0.3);
  doc.line(0, y + 12, W, y + 12);
  return y + 18;
}

function addSectionTitle(doc, y, text) {
  const W = doc.internal.pageSize.getWidth();
  doc.setFillColor(...BRAND_BLUE);
  doc.rect(14, y, 4, 7, "F");
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...BRAND_DARK);
  doc.text(text, 22, y + 6);
  doc.setDrawColor(226, 232, 240);
  doc.setLineWidth(0.3);
  doc.line(14, y + 9, W - 14, y + 9);
  return y + 16;
}

function addFooter(doc, pageNum) {
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  doc.setFillColor(...BRAND_DARK);
  doc.rect(0, H - 12, W, 12, "F");
  doc.setTextColor(122, 215, 240);
  doc.setFontSize(7);
  doc.setFont("helvetica", "normal");
  doc.text("INGRES — Central Ground Water Board (CGWB) Data | For academic and research use only", 14, H - 4);
  doc.setTextColor(186, 233, 247);
  doc.text(`Page ${pageNum}`, W - 14, H - 4, { align: "right" });
}

function addCategoryBadge(doc, x, y, category) {
  const rgb = getCategoryRgb(category);
  const w = doc.getTextWidth(category) + 6;
  doc.setFillColor(rgb[0], rgb[1], rgb[2], 0.15);
  doc.setFillColor(rgb[0] + 180, rgb[1] + 60, rgb[2] + 60);
  doc.setFillColor(...rgb.map(v => Math.min(255, v + 150)));
  doc.roundedRect(x, y - 4, w, 6, 1.5, 1.5, "F");
  doc.setTextColor(...rgb);
  doc.setFontSize(7.5);
  doc.setFont("helvetica", "bold");
  doc.text(category, x + 3, y);
  return x + w + 4;
}

async function captureChart(canvasRef) {
  if (!canvasRef || !canvasRef.current) return null;
  try {
    const canvas = canvasRef.current.canvas || canvasRef.current;
    return canvas.toDataURL("image/png");
  } catch {
    return null;
  }
}

async function captureElement(selector) {
  const el = document.querySelector(selector);
  if (!el) return null;
  try {
    const canvas = await html2canvas(el, { scale: 1.5, useCORS: true, backgroundColor: "#ffffff" });
    return canvas.toDataURL("image/png");
  } catch {
    return null;
  }
}

export async function exportDashboardPDF({ stats, distribution, topRisk, modelStats }) {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const rid = reportId();
  let y = addHeader(doc, "Dashboard Report", "National Groundwater Overview");
  y = addMetaRow(doc, y, rid);

  y = addSectionTitle(doc, y, "National Overview Statistics");

  const statItems = [
    ["Total Blocks Assessed", stats?.total_blocks?.toLocaleString() || "—"],
    ["States Covered", stats?.total_states || "—"],
    ["Over-Exploited Blocks", stats?.over_exploited_blocks?.toLocaleString() || "—"],
    ["Safe Blocks", stats?.safe_blocks?.toLocaleString() || "—"],
    ["Average Extraction Rate", `${stats?.avg_extraction || "—"}%`],
    ["Over-Exploited %", `${stats?.over_exploited_pct || "—"}%`],
  ];

  autoTable(doc, {
    startY: y,
    head: [["Metric", "Value"]],
    body: statItems,
    margin: { left: 14, right: 14 },
    headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
    bodyStyles: { fontSize: 9, textColor: [30, 40, 50] },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    columnStyles: { 0: { fontStyle: "bold", cellWidth: 90 }, 1: { cellWidth: 80 } },
  });
  y = doc.lastAutoTable.finalY + 10;

  y = addSectionTitle(doc, y, "Category Distribution");
  const distBody = distribution.map(d => [
    d.category, d.count.toLocaleString(), `${d.percentage}%`
  ]);
  autoTable(doc, {
    startY: y,
    head: [["Category", "Block Count", "Percentage"]],
    body: distBody,
    margin: { left: 14, right: 14 },
    headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
    bodyStyles: { fontSize: 9 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    didDrawCell: (data) => {
      if (data.section === "body" && data.column.index === 0) {
        const cat = data.cell.raw;
        const rgb = getCategoryRgb(cat);
        doc.setFillColor(...rgb);
        doc.rect(data.cell.x + 2, data.cell.y + data.cell.height / 2 - 1.5, 3, 3, "F");
      }
    },
  });
  y = doc.lastAutoTable.finalY + 10;

  if (y > 220) { doc.addPage(); y = addHeader(doc, "Dashboard Report", "continued"); y = addMetaRow(doc, y, rid); }

  y = addSectionTitle(doc, y, "Top At-Risk Districts");
  const riskBody = topRisk.map((d, i) => [
    i + 1, d.district || d.state, d.state, `${d.extraction}%`, d.category
  ]);
  autoTable(doc, {
    startY: y,
    head: [["#", "District", "State", "Extraction", "Category"]],
    body: riskBody,
    margin: { left: 14, right: 14 },
    headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
    bodyStyles: { fontSize: 8.5 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    didDrawCell: (data) => {
      if (data.section === "body" && data.column.index === 4) {
        const cat = data.cell.raw;
        const rgb = getCategoryRgb(cat);
        doc.setTextColor(...rgb);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(8);
        doc.text(cat, data.cell.x + 2, data.cell.y + data.cell.height / 2 + 1);
        doc.setTextColor(30, 40, 50);
        doc.setFont("helvetica", "normal");
        return false;
      }
    },
  });
  y = doc.lastAutoTable.finalY + 10;

  if (modelStats) {
    if (y > 210) { doc.addPage(); y = addHeader(doc, "Dashboard Report", "Model Statistics"); y = addMetaRow(doc, y, rid); }
    y = addSectionTitle(doc, y, "ML Model Performance");
    const clfBody = [
      ["SVM", `${modelStats.classifiers?.svm?.accuracy}%`, "Classification", modelStats.classifiers?.best_model === "svm" ? "BEST" : ""],
      ["Random Forest", `${modelStats.classifiers?.random_forest?.accuracy}%`, "Classification", modelStats.classifiers?.best_model === "random_forest" ? "BEST" : ""],
      ["Decision Tree", `${modelStats.classifiers?.decision_tree?.accuracy}%`, "Classification", modelStats.classifiers?.best_model === "decision_tree" ? "BEST" : ""],
      ["Linear Regression", `RMSE: ${modelStats.regressors?.linear_regression?.rmse}`, "Regression", modelStats.regressors?.best_model === "linear_regression" ? "BEST" : ""],
      ["Random Forest Reg.", `RMSE: ${modelStats.regressors?.random_forest?.rmse}  R²: ${modelStats.regressors?.random_forest?.r2}`, "Regression", modelStats.regressors?.best_model === "random_forest" ? "BEST" : ""],
    ];
    autoTable(doc, {
      startY: y,
      head: [["Model", "Performance", "Task", "Status"]],
      body: clfBody,
      margin: { left: 14, right: 14 },
      headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
      bodyStyles: { fontSize: 8.5 },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      didDrawCell: (data) => {
        if (data.section === "body" && data.column.index === 3 && data.cell.raw === "BEST") {
          doc.setTextColor(...BRAND_BLUE);
          doc.setFont("helvetica", "bold");
        }
      },
    });
  }

  const totalPages = doc.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i);
    addFooter(doc, i);
  }

  doc.save(`INGRES_Dashboard_Report_${Date.now()}.pdf`);
}

export async function exportPredictionPDF({ riskResult, predResult, state, extractionPct, targetYear, chartRef }) {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const rid = reportId();
  let y = addHeader(doc, "Prediction Report", `${state || "India"} — Groundwater Analysis`);
  y = addMetaRow(doc, y, rid);

  y = addSectionTitle(doc, y, "Input Parameters");
  const inputBody = [
    ["State / Region", state || "Not specified"],
    ["Current Extraction Rate", extractionPct != null ? `${extractionPct}%` : "—"],
    ["Target Forecast Year", targetYear || "—"],
  ];
  autoTable(doc, {
    startY: y,
    body: inputBody,
    margin: { left: 14, right: 14 },
    bodyStyles: { fontSize: 9, textColor: [30, 40, 50] },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    columnStyles: { 0: { fontStyle: "bold", cellWidth: 80 } },
  });
  y = doc.lastAutoTable.finalY + 10;

  if (riskResult && !riskResult.error) {
    y = addSectionTitle(doc, y, "Risk Classification Result");

    const rgb = getCategoryRgb(riskResult.category);
    doc.setFillColor(...rgb.map(v => Math.min(255, v + 150)));
    doc.roundedRect(14, y, W - 28, 18, 3, 3, "F");
    doc.setFillColor(...rgb);
    doc.roundedRect(14, y, 5, 18, 2, 2, "F");
    doc.setTextColor(...rgb);
    doc.setFontSize(13);
    doc.setFont("helvetica", "bold");
    doc.text(riskResult.category, 24, y + 7);
    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(80, 80, 80);
    doc.text(`Predicted risk category based on extraction: ${riskResult.input?.extraction_pct}%`, 24, y + 14);
    y += 24;

    const probBody = Object.entries(riskResult.probabilities || {}).map(([cat, prob]) => [cat, `${prob}%`]);
    autoTable(doc, {
      startY: y,
      head: [["Category", "Probability"]],
      body: probBody,
      margin: { left: 14, right: 14 },
      headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
      bodyStyles: { fontSize: 9 },
      alternateRowStyles: { fillColor: [248, 250, 252] },
    });
    y = doc.lastAutoTable.finalY + 10;

    const inp = riskResult.input || {};
    y = addSectionTitle(doc, y, "Feature Values Used for Classification");
    autoTable(doc, {
      startY: y,
      body: [
        ["Extraction Rate", `${inp.extraction_pct}%`],
        ["Recharge Level", `${inp.recharge_level} mm`],
        ["Rainfall", `${inp.rainfall_mm} mm`],
        ["Population Density", `${inp.population_density}/km²`],
      ],
      margin: { left: 14, right: 14 },
      bodyStyles: { fontSize: 9 },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      columnStyles: { 0: { fontStyle: "bold", cellWidth: 80 } },
    });
    y = doc.lastAutoTable.finalY + 10;
  }

  if (predResult && !predResult.error) {
    if (y > 200) { doc.addPage(); y = addHeader(doc, "Prediction Report", "Extraction Forecast"); y = addMetaRow(doc, y, rid); }
    y = addSectionTitle(doc, y, "Extraction Forecast");

    const rgb = getCategoryRgb(predResult.category);
    doc.setFillColor(...rgb.map(v => Math.min(255, v + 150)));
    doc.roundedRect(14, y, W - 28, 18, 3, 3, "F");
    doc.setFillColor(...rgb);
    doc.roundedRect(14, y, 5, 18, 2, 2, "F");
    doc.setTextColor(...rgb);
    doc.setFontSize(13);
    doc.setFont("helvetica", "bold");
    doc.text(`${predResult.predicted_extraction}%`, 24, y + 7);
    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(80, 80, 80);
    doc.text(`Predicted extraction for ${predResult.year} — Status: ${predResult.category}`, 24, y + 14);
    y += 24;

    if (predResult.trend_forecast?.length) {
      autoTable(doc, {
        startY: y,
        head: [["Year", "Predicted Extraction (%)"]],
        body: predResult.trend_forecast.map(t => [t.year, `${t.predicted_extraction}%`]),
        margin: { left: 14, right: 14 },
        headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
        bodyStyles: { fontSize: 9 },
        alternateRowStyles: { fillColor: [248, 250, 252] },
      });
      y = doc.lastAutoTable.finalY + 10;
    }
  }

  if (chartRef) {
    const img = await captureChart(chartRef);
    if (img) {
      if (y > 180) { doc.addPage(); y = addHeader(doc, "Prediction Report", "Forecast Chart"); y = addMetaRow(doc, y, rid); }
      y = addSectionTitle(doc, y, "6-Year Extraction Forecast Chart");
      const imgW = W - 28;
      const imgH = imgW * 0.45;
      doc.addImage(img, "PNG", 14, y, imgW, imgH);
      y += imgH + 10;
    }
  }

  const totalPages = doc.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) { doc.setPage(i); addFooter(doc, i); }
  doc.save(`INGRES_Prediction_Report_${Date.now()}.pdf`);
}

export async function exportComparisonPDF({ results, chartSelector }) {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const rid = reportId();
  let y = addHeader(doc, "District Comparison Report", "Side-by-Side Groundwater Analysis");
  y = addMetaRow(doc, y, rid);
  y = addSectionTitle(doc, y, `Comparing ${results.length} Locations`);

  const compBody = results.map((r, i) => [
    i + 1, r.name, r.state?.charAt(0).toUpperCase() + r.state?.slice(1) || "—",
    `${r.extraction}%`, `${r.recharge_estimate}%`, r.category
  ]);
  autoTable(doc, {
    startY: y,
    head: [["#", "Location", "State", "Extraction", "Est. Recharge", "Category"]],
    body: compBody,
    margin: { left: 14, right: 14 },
    headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
    bodyStyles: { fontSize: 9 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    didDrawCell: (data) => {
      if (data.section === "body" && data.column.index === 5) {
        const cat = data.cell.raw;
        const rgb = getCategoryRgb(cat);
        doc.setTextColor(...rgb);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(8);
        doc.text(cat, data.cell.x + 2, data.cell.y + data.cell.height / 2 + 1);
        doc.setTextColor(30, 40, 50);
        doc.setFont("helvetica", "normal");
        return false;
      }
    },
  });
  y = doc.lastAutoTable.finalY + 10;

  y = addSectionTitle(doc, y, "Analysis Summary");
  const highest = results.reduce((a, b) => a.extraction > b.extraction ? a : b, results[0]);
  const lowest = results.reduce((a, b) => a.extraction < b.extraction ? a : b, results[0]);
  const avg = (results.reduce((s, r) => s + r.extraction, 0) / results.length).toFixed(1);
  autoTable(doc, {
    startY: y,
    body: [
      ["Highest Extraction", `${highest?.name} — ${highest?.extraction}% (${highest?.category})`],
      ["Lowest Extraction", `${lowest?.name} — ${lowest?.extraction}% (${lowest?.category})`],
      ["Average Extraction", `${avg}%`],
      ["Locations Compared", results.length],
    ],
    margin: { left: 14, right: 14 },
    bodyStyles: { fontSize: 9 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    columnStyles: { 0: { fontStyle: "bold", cellWidth: 70 } },
  });
  y = doc.lastAutoTable.finalY + 10;

  if (chartSelector) {
    const img = await captureElement(chartSelector);
    if (img) {
      if (y > 170) { doc.addPage(); y = addHeader(doc, "Comparison Report", "Chart"); y = addMetaRow(doc, y, rid); }
      y = addSectionTitle(doc, y, "Comparison Chart");
      const imgW = W - 28;
      doc.addImage(img, "PNG", 14, y, imgW, imgW * 0.5);
    }
  }

  const totalPages = doc.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) { doc.setPage(i); addFooter(doc, i); }
  doc.save(`INGRES_Comparison_Report_${Date.now()}.pdf`);
}

export async function exportTrendsPDF({ trends, years, selectedStates }) {
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const W = doc.internal.pageSize.getWidth();
  const rid = reportId();
  let y = addHeader(doc, "Trend Analysis Report", "Historical Groundwater Extraction (2017–2022)");
  y = addMetaRow(doc, y, rid);

  const displayed = selectedStates?.length
    ? trends.filter(t => selectedStates.includes(t.state))
    : trends;

  y = addSectionTitle(doc, y, `Extraction Trends — ${displayed.length} States`);

  const head = ["State", ...years.map(String), "Latest", "Category"];
  const body = displayed.map(t => {
    const vals = years.map(yr => {
      const v = t.values?.find(x => x.year === yr);
      return v ? `${v.extraction}%` : "—";
    });
    return [
      t.state.charAt(0).toUpperCase() + t.state.slice(1),
      ...vals,
      `${t.latest_extraction}%`,
      t.category,
    ];
  });

  autoTable(doc, {
    startY: y,
    head: [head],
    body,
    margin: { left: 14, right: 14 },
    headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 8 },
    bodyStyles: { fontSize: 8 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    didDrawCell: (data) => {
      if (data.section === "body" && data.column.index === head.length - 1) {
        const cat = data.cell.raw;
        const rgb = getCategoryRgb(cat);
        doc.setTextColor(...rgb);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(7.5);
        doc.text(cat, data.cell.x + 2, data.cell.y + data.cell.height / 2 + 1);
        doc.setTextColor(30, 40, 50);
        doc.setFont("helvetica", "normal");
        return false;
      }
    },
  });

  y = doc.lastAutoTable.finalY + 10;
  if (y < doc.internal.pageSize.getHeight() - 30) {
    y = addSectionTitle(doc, y, "Category Summary");
    const cats = ["Safe", "Semi-Critical", "Critical", "Over-Exploited"];
    const catCounts = cats.map(c => [c, displayed.filter(t => t.category === c).length]);
    autoTable(doc, {
      startY: y,
      head: [["Category", "State Count"]],
      body: catCounts,
      margin: { left: 14, right: 14 },
      headStyles: { fillColor: BRAND_DARK, textColor: [255, 255, 255], fontStyle: "bold", fontSize: 9 },
      bodyStyles: { fontSize: 9 },
      tableWidth: 80,
    });
  }

  const totalPages = doc.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) { doc.setPage(i); addFooter(doc, i); }
  doc.save(`INGRES_Trend_Analysis_Report_${Date.now()}.pdf`);
}

export function exportComparisonCSV(results) {
  const headers = ["#", "Location", "State", "Extraction (%)", "Est. Recharge (%)", "Category"];
  const rows = results.map((r, i) => [
    i + 1,
    r.name,
    r.state?.charAt(0).toUpperCase() + r.state?.slice(1) || "",
    r.extraction,
    r.recharge_estimate,
    r.category,
  ]);
  const highest = results.reduce((a, b) => a.extraction > b.extraction ? a : b, results[0]);
  const lowest = results.reduce((a, b) => a.extraction < b.extraction ? a : b, results[0]);
  const avg = (results.reduce((s, r) => s + r.extraction, 0) / results.length).toFixed(1);
  const summary = [
    [],
    ["Summary"],
    ["Highest Extraction", highest?.name, "", highest?.extraction + "%", "", highest?.category],
    ["Lowest Extraction", lowest?.name, "", lowest?.extraction + "%", "", lowest?.category],
    ["Average Extraction", "", "", avg + "%", "", ""],
    ["Generated", timestamp()],
    ["Report ID", reportId()],
  ];
  const csvRows = [headers, ...rows, ...summary].map(r =>
    r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")
  );
  downloadCSV(csvRows.join("\n"), `INGRES_Comparison_${Date.now()}.csv`);
}

export function exportTrendsCSV(trends, years) {
  const headers = ["State", ...years.map(String), "Latest (%)", "Category"];
  const rows = trends.map(t => {
    const vals = years.map(yr => {
      const v = t.values?.find(x => x.year === yr);
      return v ? v.extraction : "";
    });
    return [
      t.state.charAt(0).toUpperCase() + t.state.slice(1),
      ...vals,
      t.latest_extraction,
      t.category,
    ];
  });
  const footer = [[], ["Generated", timestamp()], ["Report ID", reportId()]];
  const csvRows = [headers, ...rows, ...footer].map(r =>
    r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")
  );
  downloadCSV(csvRows.join("\n"), `INGRES_Trend_Analysis_${Date.now()}.csv`);
}

export function exportDashboardCSV(stats, distribution, topRisk) {
  const lines = [
    ["INGRES — National Overview Report"],
    ["Generated", timestamp()],
    [],
    ["OVERVIEW STATISTICS"],
    ["Metric", "Value"],
    ["Total Blocks", stats?.total_blocks],
    ["Total States", stats?.total_states],
    ["Over-Exploited Blocks", stats?.over_exploited_blocks],
    ["Safe Blocks", stats?.safe_blocks],
    ["Avg Extraction (%)", stats?.avg_extraction],
    ["Over-Exploited %", stats?.over_exploited_pct],
    [],
    ["CATEGORY DISTRIBUTION"],
    ["Category", "Count", "Percentage"],
    ...distribution.map(d => [d.category, d.count, d.percentage + "%"]),
    [],
    ["TOP AT-RISK DISTRICTS"],
    ["Rank", "District", "State", "Extraction (%)", "Category"],
    ...topRisk.map((d, i) => [i + 1, d.district || d.state, d.state, d.extraction, d.category]),
  ];
  const csv = lines.map(r =>
    r.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")
  ).join("\n");
  downloadCSV(csv, `INGRES_Dashboard_${Date.now()}.csv`);
}

export function exportPredictionCSV(riskResult, predResult, state) {
  const lines = [
    ["INGRES — Prediction Report"],
    ["State", state || "Not specified"],
    ["Generated", timestamp()],
    [],
  ];
  if (riskResult && !riskResult.error) {
    lines.push(
      ["RISK CLASSIFICATION"],
      ["Predicted Category", riskResult.category],
      ["Extraction Input", riskResult.input?.extraction_pct + "%"],
      ["Recharge Level", riskResult.input?.recharge_level + " mm"],
      ["Rainfall", riskResult.input?.rainfall_mm + " mm"],
      ["Population Density", riskResult.input?.population_density + "/km²"],
      [],
      ["PROBABILITIES"],
      ["Category", "Probability (%)"],
      ...Object.entries(riskResult.probabilities || {}).map(([k, v]) => [k, v]),
      []
    );
  }
  if (predResult && !predResult.error) {
    lines.push(
      ["EXTRACTION FORECAST"],
      ["Year", predResult.year],
      ["Predicted Extraction", predResult.predicted_extraction + "%"],
      ["Predicted Category", predResult.category],
      [],
      ["6-YEAR TREND FORECAST"],
      ["Year", "Predicted Extraction (%)"],
      ...(predResult.trend_forecast || []).map(t => [t.year, t.predicted_extraction]),
    );
  }
  const csv = lines.map(r =>
    r.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")
  ).join("\n");
  downloadCSV(csv, `INGRES_Prediction_${Date.now()}.csv`);
}

function downloadCSV(content, filename) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

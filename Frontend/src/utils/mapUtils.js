export const getColor = (depth) => {
  if (depth <= 2) return "#2ecc71"; // Green
  if (depth <= 5) return "#00b894"; // Tropical Green
  if (depth <= 10) return "#f1c40f"; // Yellow
  if (depth <= 20) return "#e67e22"; // Orange
  if (depth <= 40) return "#e74c3c"; // Red
  return "#8b0000"; // Dark Red for >40
};

export const legendItems = [
  { color: "#2ecc71", label: "Very Shallow (0-2 mbgl)" },
  { color: "#00b894", label: "Shallow (2-5 mbgl)" },
  { color: "#f1c40f", label: "Moderate (5-10 mbgl)" },
  { color: "#e67e22", label: "Moderately Deep (10-20 mbgl)" },
  { color: "#e74c3c", label: "Deep (20-40 mbgl)" },
  { color: "#8b0000", label: "Very Deep (>40 mbgl)" },
];

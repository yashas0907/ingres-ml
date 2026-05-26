import React, { useState } from "react";
import MapLegend from "./components/MapLegend";
import { karnatakaDistrictPaths } from "./data/karnataka_paths";
import { karnatakaDistrictData } from "./data/karnataka_groundwater";
import { contaminantData } from "./data/contaminants";
import { getColor } from "./utils/mapUtils";

const KarnatakaMap = ({ onBack }) => {
  const [hoveredDistrict, setHoveredDistrict] = useState(null);
  const [selectedDistrict, setSelectedDistrict] = useState(null);

  // Show hovered district info, or selected, or placeholder
  const displayDistrict = hoveredDistrict || selectedDistrict;

  return (
    <div className="map-container karnataka-map" role="region" aria-label="Karnataka Groundwater Depth Map">
      <div className="map-header">
        <button className="back-btn" onClick={onBack}>
          ← Back to India Map
        </button>
        <h2 className="map-title">Karnataka State - District Wise Levels</h2>
      </div>

      <div className="state-details">
        {displayDistrict ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <div className="state-main-info">
              <span className="state-name">{displayDistrict}</span>
              <span className="state-value">{karnatakaDistrictData[displayDistrict] || "N/A"} mbgl</span>
            </div>
            {contaminantData[displayDistrict] && (
              <div className="contaminant-warning" style={{ fontSize: "0.85rem", opacity: 0.9 }}>
                Contaminants: {contaminantData[displayDistrict].join(", ")}
              </div>
            )}
          </div>
        ) : (
          <div className="placeholder">Hover over or click a district for details</div>
        )}
      </div>

      <div className="map-wrapper karnataka-wrapper">
        <svg
          viewBox="0 0 600 800"
          className="karnataka-svg"
          preserveAspectRatio="xMidYMid meet"
          style={{ width: "100%", height: "auto", maxHeight: "600px" }}
        >
          {Object.entries(karnatakaDistrictPaths).map(([name, path]) => (
            <path
              key={name}
              d={path}
              fill={getColor(karnatakaDistrictData[name]) || "#eee"}
              stroke="#fff"
              strokeWidth="1"
              onMouseEnter={() => setHoveredDistrict(name)}
              onMouseLeave={() => setHoveredDistrict(null)}
              onClick={() => setSelectedDistrict(name)}
              className="district-path"
              style={{ cursor: "pointer" }}
            >
              <title>{name}: {karnatakaDistrictData[name] || "N/A"} mbgl</title>
            </path>
          ))}
        </svg>
      </div>

      <MapLegend />
    </div>
  );
};

export default KarnatakaMap;

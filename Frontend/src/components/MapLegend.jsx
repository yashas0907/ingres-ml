import React from "react";
import { legendItems } from "../utils/mapUtils";

const MapLegend = () => {
  return (
    <div className="map-legend">
      <h3>Depth to Water Level (mbgl)</h3>
      <div className="legend-items">
        {legendItems.map((item, index) => (
          <div key={index} className="legend-item">
            <span className="box" style={{ backgroundColor: item.color }}></span>
            <span>{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MapLegend;

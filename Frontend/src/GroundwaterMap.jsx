import React, { useState } from "react";
import IndiaMap from "@react-map/india";
import KarnatakaMap from "./KarnatakaMap";
import MapLegend from "./components/MapLegend";
import { groundwaterData } from "./data/groundwater";
import { contaminantData } from "./data/contaminants";
import { getColor } from "./utils/mapUtils";

const GroundwaterMap = () => {
  const [selectedState, setSelectedState] = useState(null);
  const [view, setView] = useState("india"); // "india" or "karnataka"
  const [selectedYear, setSelectedYear] = useState(2022);
  const [mapSize, setMapSize] = useState(window.innerWidth < 768 ? 350 : 600);

  React.useEffect(() => {
    const handleResize = () => {
      setMapSize(window.innerWidth < 768 ? 350 : 600);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const currentYearData = groundwaterData[selectedYear] || {};

  const cityColors = {};
  Object.keys(currentYearData).forEach((state) => {
    cityColors[state] = getColor(currentYearData[state]);
  });

  const handleSelect = (state) => {
    setSelectedState(state);
    if (state === "Karnataka") {
      setView("karnataka");
    }
  };

  if (view === "karnataka") {
    return <KarnatakaMap onBack={() => setView("india")} />;
  }

  return (
    <div className="map-container" role="region" aria-label="India Groundwater Depth Map">
      <div className="map-controls">
        <label htmlFor="year-select">Select Year: </label>
        <select
          id="year-select"
          value={selectedYear}
          onChange={(e) => setSelectedYear(parseInt(e.target.value))}
          className="year-dropdown"
        >
          <option value={2021}>2021</option>
          <option value={2022}>2022</option>
          <option value={2023}>2023</option>
        </select>
      </div>

      {selectedState ? (
        <div className="state-details">
          <div className="state-main-info">
            <span className="state-name">{selectedState}</span>
            <span className="state-value">{currentYearData[selectedState] || "Data not available"} mbgl</span>
          </div>
          {contaminantData[selectedState] && (
            <div className="contaminant-warning">
              Contaminants: {contaminantData[selectedState].join(", ")}
            </div>
          )}
        </div>
      ) : (
        <div className="state-details placeholder">
          Click on a state to view depth details
        </div>
      )}
      <div className="map-wrapper">
        <IndiaMap
          type="select-single"
          size={mapSize}
          mapColor="#eee"
          strokeColor="#fff"
          strokeWidth={0.5}
          cityColors={cityColors}
          hints={true}
          hintBackgroundColor="white"
          hintTextColor="black"
          onSelect={handleSelect}
        />
      </div>

      <MapLegend />
    </div>
  );
};

export default GroundwaterMap;

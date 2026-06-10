import { Routes, Route } from "react-router-dom";
import TopBar from "../components/chrome/TopBar";
import StatusBar from "../components/chrome/StatusBar";
import MapView from "../components/MapView";
import StatsPanel from "../components/StatsPanel";
import DatasetList from "../components/DatasetList";
import DatasetDetail from "../components/DatasetDetail";

export default function DashboardPage() {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gotham-900 text-gotham-100">
      {/* Classification banner — Gotham-Zitat */}
      <div className="flex h-5 shrink-0 items-center justify-center bg-gotham-750">
        <span className="font-mono text-[9px] uppercase tracking-[0.34em] text-signal-cyan/80">
          Unklassifiziert&nbsp;//&nbsp;Offene Verwaltungsdaten&nbsp;—&nbsp;Stadt Leipzig
        </span>
      </div>

      <TopBar />

      <main className="relative flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<MapView />} />
          <Route path="/stats" element={<StatsPanel />} />
          <Route path="/datasets" element={<DatasetList />} />
          <Route path="/datasets/:datasetId" element={<DatasetDetail />} />
        </Routes>
      </main>

      <StatusBar />
    </div>
  );
}

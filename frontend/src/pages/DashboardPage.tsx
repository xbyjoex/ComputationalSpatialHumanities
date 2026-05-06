import { Routes, Route } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import MapView from "../components/MapView";
import StatsPanel from "../components/StatsPanel";
import DatasetList from "../components/DatasetList";

export default function DashboardPage() {
  return (
    <div className="flex h-screen overflow-hidden bg-slate-900">
      <Sidebar />
      <main className="flex-1 relative">
        <Routes>
          <Route path="/" element={<MapView />} />
          <Route path="/stats" element={<StatsPanel />} />
          <Route path="/datasets" element={<DatasetList />} />
        </Routes>
      </main>
    </div>
  );
}

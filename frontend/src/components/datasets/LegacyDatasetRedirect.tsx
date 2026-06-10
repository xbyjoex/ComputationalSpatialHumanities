import { useQuery } from "react-query";
import { Navigate, useParams } from "react-router-dom";
import { getDataset } from "../../api/datasets";

/** Alte UUID-URLs (/datasets/<uuid>) auf die Slug-Route umleiten. */
export default function LegacyDatasetRedirect() {
  const { datasetId = "" } = useParams<{ datasetId: string }>();
  const { data, isError } = useQuery(
    ["dataset", datasetId],
    () => getDataset(datasetId),
    { enabled: !!datasetId, retry: false }
  );

  if (isError) return <Navigate to="/datasets" replace />;
  if (!data) {
    return (
      <div className="blueprint-bg h-full p-8">
        <p className="font-mono text-xs text-gotham-500">
          <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
          Leite weiter …
        </p>
      </div>
    );
  }
  return (
    <Navigate
      to={`/datasets/d/${encodeURIComponent(data.dataset.name ?? datasetId)}`}
      replace
    />
  );
}

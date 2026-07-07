import { apiClient } from "./client";

/** Symmetrischer Score-Wertebereich der Farbskala (Werte werden geclampt). */
export const SPECTRUM_DOMAIN = 0.5;
export const SONSTIGE_COLOR = "#6b7683";

export interface SpectrumPartyShare {
  key: string | null;
  name: string;
  share: number;
  color: string;
}

export interface SpectrumFeatureProps {
  gebiet_code: string;
  name: string;
  score: number | null;
  coverage_pct: number;
  turnout_pct: number | null;
  parties: SpectrumPartyShare[];
}

export interface SpectrumYear {
  year: number;
  levels: string[];
}

export interface SpectrumElection {
  election_type: string;
  title: string;
  years: SpectrumYear[];
}

export interface SpectrumOptions {
  elections: SpectrumElection[];
  parties: { key: string; name: string; position: number | null; color: string }[];
}

export const fetchSpectrumOptions = (): Promise<SpectrumOptions> =>
  apiClient.get("/elections/spectrum/options").then((r) => r.data);

export const fetchSpectrum = (election_type: string, year: number, level: string) =>
  apiClient
    .get("/elections/spectrum", { params: { election_type, year, level } })
    .then((r) => r.data);

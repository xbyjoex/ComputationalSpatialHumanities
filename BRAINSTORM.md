# Quant/Game-Theory Reframe: Drei Projekte mit Live-Komponente

## Bottom Line vorweg

Mit deinem Fokus (spieltheoretisch / wirtschaftlich / live) ändert sich die Rangfolge **stark**:

1. **Iran Hormuz als Strategic-Choke-Point-Pricing-Modell** → klarer **Top-Pick**. Die laufende 2026er Krise ist ein außergewöhnliches Naturexperiment: War Risk Premiums, Brent-Backwardation, AIS-Tankerverkehr und FT/WSJ/Barron's-Coverage sind alle live verfügbar und bilden Spieltheorie *direkt* ab — Iran als Threat-Sender, Insurance Market als Belief-Updater, Brent als Outcome-Variable.
2. **Iran-Wasser als Hydropolitisches Bargaining-Game** → methodisch ambitionierteste Variante (Helmand × Aras × Tigris-Euphrat als parallele Spiele).
3. **Leipzig Immobilien als Quantitative Investment Engine** → sicherster Pfad, aber **nutzt deine Abos kaum** und hat schwächere Live-Komponente.

---

## Idee 1 — Hormuz: The Strait Risk Tape ★ Top-Pick

### Konzept
**"The Strait Risk Tape: A Live Quantitative Dashboard for the World's Most Expensive Maritime Choke Point"**

Operationalisiert die Hormuz-Krise als **strategisches Bargaining-Spiel** zwischen Iran, USA/Allies und dem privaten Versicherungsmarkt. Topographie tritt nicht als Angreifer-Perspektive auf, sondern als **strukturelle Verhandlungsmacht** (Anti-Ship-Missile-Sites entlang Zagros-Küste, mountain-protected UAV-Bases auf Qeshm/Bandar-e-Jask, Bypass-Pipeline-Geographie).

**Forschungsfragen**:
- Wie schnell preisen Brent, AWRP (Additional War Risk Premium) und VLCC-Frachtraten Eskalations-Events ein? Diskrete Belief-Updates messbar?
- Welches Modell erklärt Irans Closure-Threat-Verhalten — Schelling-Brinkmanship, Powell-Crisis-Bargaining, Fearon'sche commitment problems?
- Wie verändert sich Threat-Credibility über Zeit (Markt-Lerneffekt bei wiederholten Drohungen)?
- Welche Bypass-Routen sind ökonomisch viable (Saudi East-West Petroline 5–7 Mb/d, UAE Habshan-Fujairah 1.5 Mb/d, IMEC) — mit welchem Topographie-/Risiko-Profil?

### Datenquellen — alle live oder near-real-time

**Energiepreise (Sekunden-Latenz)**
- `yfinance`: Brent (`BZ=F`), WTI (`CL=F`), Dubai, Natural Gas, USO/BNO, Energy ETFs (XLE, XOP), VIX, USD-Index — kostenfrei
- ICE Brent Futures Curve für Backwardation
- `oilpriceapi.com` Free-Tier (10k req/Monat) als Backup
- EIA STEO + Weekly Petroleum Status Report

**AIS-Tanker (15–60 Min)**
- **Global Fishing Watch APIs** (`gfw-api-python-client`, kostenfreie Forschungsregistrierung): 4Wings + Vessels + Events. Hormuz-Bounding-Box, Tanker-Filter via vessel type
- Stationary-Vessel-Detection: 10+ Tage = "stranded" → ~40 LR-Tanker im Persian Gulf gestrandet ist genau die Story

**Insurance Premium Time Series — der wertvollste Abo-Use-Case!**
AWRP-Levels sind nirgends als API verfügbar (OTC-Markt). Aber die Werte werden regelmäßig in FT/WSJ/Barron's, S&P Platts, Reuters, Lloyd's List zitiert. Konkrete Datapoints, die ich gefunden habe:

- **Pre-Crisis** (Jan 2026): 0.02–0.05% / 0.125% Hull&Machinery-Wert pro 7 Tage
- **18.–25. Feb 2026** (Pre-Strike): 0.2–0.4%
- **Anfang März** (Peak): 2.5%
- **Ende März**: ~1%
- **Mitte April**: 3.5–10% (McGill & Partners) bzw. 0.5–1% (Forgione)

→ **Eigene Methode**: Aufbau eines **Premium-Tracking-Korpus** aus FT/WSJ/Barron's + Lloyd's List + Splash247 + S&P Platts News, mit spaCy-NER-Pattern für `"X% (war risk|AWRP|Hull and Machinery)"` + manueller Validierung. Das wäre ein **eigenständiger Datenbeitrag**, der so nirgends öffentlich aggregiert vorliegt.

**Bypass-Routen / Geo-Layer**
- Global Energy Monitor Pipeline-Tracker (CC-BY-4.0)
- Copernicus DEM GLO-30 für Topographie iranische Küste
- OSM Overpass für Häfen, Pipelines, Raffinerien
- **CFTC Commitments of Traders (COT)** wöchentlich: Money Manager Long/Short Brent als Speculator-Sentiment-Proxy

**News / Sentiment**
- **FT Headlines API** (developer.ft.com/portal/) — kostenlos für Abonnenten, akademisch erlaubt; Headlines + URLs + Tags
- **WSJ + Barron's**: Text-Mining ist ToS-verboten, aber **manuelle Stichprobe** (50–100 Schlüsselartikel) + Headline-Sammlung via RSS/Newsletter ist legitim
- **GDELT 2.0** als Multi-Source-Korpus (Achtung BigQuery: immer mit `_PARTITIONTIME` filtern)
- **ACLED**: Tanker-Attacks/Mine-Incidents als Event-Datenbank für Event-Study-Definitions

### Spieltheoretische Modellierung

**Methodenrahmen**:
- Schelling 1960 *Strategy of Conflict* — Brinkmanship als gemischte Strategie
- Powell 2002 *Bargaining Theory of War* (APSR) — Iran als revisionist actor
- Fearon 1995 *Rationalist Explanations* — Information & Commitment Problems

**Implementierung**:
- **Bayesian Game** Iran (Type: Resolved vs. Bluffing) × USA (Belief μ), Nash-Equilibria via `nashpy` oder `gambit-project`
- **Threat-Credibility-Decay**: ΔAWRP / Eskalationsereignis als empirischer Decay-Rate; Hypothese: nach 3+ Drohungen ohne Closure sinkt Premium-Reaktion (Markt-Lernen — empirisch testbar)
- **Eskalations-Ladder mit historischen Anchor-Points**: Tanker War 1984, Stena Impero 2019, Houthi Red Sea 2024, 2026 Crisis auf einheitlicher Premium-Skala
- **Bypass-Lerner-Index**: Wenn Bypässe X Mb/d ersetzen, sinkt Closure-Threat-Wirksamkeit — quantifizierbar

### Live-Visualisierung (Streamlit/Dash)
- **Pydeck/Kepler.gl 3D-Karte**: Hormuz mit Tanker-AIS-Density + Topographie-Hillshade + Bypass-Pipelines + iranische Anti-Ship-Range-Buffer (~300 km)
- **Plotly Multi-Panel**: AWRP × Brent-Front-Month × Brent-WTI-Spread × Tanker Transit Count × News Tone — gemeinsame Achse, Event-Annotations
- **Game-Tree-Visualisierung** (D3 oder graphviz)
- **Event Study CAR Panel**: Cumulative Abnormal Return Brent für jede Eskalation
- **Risk Premium Forward Curve**: AWRP × Brent Calendar Spread als Stress-Index

### ML / Quant-Methodik
- **Event Study CAR** (MacKinlay 1997): Brent-Returns ±5 Tage um Eskalationen, Market Model mit S&P 500
- **Causal Impact** (Brodersen et al., `tfcausalimpact`): Bayesian structural time series für Counterfactual Brent ohne Closure
- **GARCH(1,1) / EGARCH** (`arch` Package); **VAR(p)** mit Brent / VIX / DXY / XLE für Spillover
- **NER + FinBERT** auf FT-Headlines für Daily Iran-Risk-Sentiment-Index
- **HDBSCAN** auf Tanker-AIS-Trajektorien für Routenwechsel-Detektion (Bypass-Diversifikation)

### Machbarkeit (4 Wochen, 2 Personen)
- **W1**: Live-Datenpipeline + Streamlit-Skeleton + DB-Schema (SQLite)
- **W2**: AWRP-Premium-Korpus + Event-Study-Framework + Topographie-Layer
- **W3**: Spieltheorie-Modul + Causal Impact + GARCH/VAR
- **W4**: Polish, Sentiment-Layer, Bericht (~15 S.) + Deck

**Risiken**: GFW-Account-Setup-Latenz (1–3 Tage), AWRP-Quotes uneinheitlich (% of value vs. $/voyage vs. 7-day-period — Vereinheitlichung wichtig), Krisendynamik kann Datenbild verschieben (Feature, nicht Bug).

### Mehrwert Abos — konkret
1. **AWRP Time Series**: FT/WSJ/Platts-Quotes liefern den einzigen public-domain-Pfad — eigenständiger Datenbeitrag
2. **FT Headlines API** als kostenfreier Live-Sentiment-Feed (Abonnenten-Privileg!)
3. **Barron's Energy Roundtable** + Broker-Notes für Event-Study-Window-Definitionen
4. **WSJ Heard on the Street + FT Lex** für qualitative Validierung der Game-Theory-Annahmen

---

## Idee 2 — Hydro-Realpolitik: Game Theory of Iran's Water Crisis

### Konzept
Drei simultane internationale Verhandlungsspiele, deren ökonomische Konsequenzen (BIP, Migration, Rial-FX, Inflation) live gemessen werden:

1. **Helmand-Game** (Iran ↓ ↔ Taliban-Afghanistan ↑): Kajaki/Kamal-Khan-Dam vs. Treaty 1973 (22 m³/s); Bargaining Chip "3 Mio. afghanische Flüchtlinge ↔ Wasserdurchfluss" — Taliban dokumentierten *"20l Diesel = 10l Wasser"*
2. **Aras-Game** (Iran ↔ Türkei ↔ Aserbaidschan): Doosti-Dam, Mashhad-Trinkwasser
3. **Tigris/Euphrat-Game** (Iran ↑ Karkheh, Karun ↔ Iraq ↓ Khuzestan): interner Conflict-Layer

**Wirtschaftliche Tiefe**: Iran-BIP-Impact (Landwirtschaft 13% BIP, 90% Bewässerung), Subventionssystem als Tragedy-of-Commons-Problem, Migration Sistan-Belutschistan (25–30% Abwanderung lt. iran. Parlament), Korrelation Wasserstress ↔ Rial-Abwertung ↔ Sanktionswirksamkeit.

### Datenquellen — live + zeitreihenstark
- **NASA GRACE/GRACE-FO TELLUS Mascon** via PO.DAAC: TWS, monatlich, 2002–heute
- **CHIRPS** (`UCSB-CHG/CHIRPS/PENTAD`): ~2-Tage-Latenz
- **TerraClimate**: SPEI, PDSI, ~4 km monatlich
- **Sentinel-2 NDWI** via Sentinel Hub Statistical API: **wirklich live** Reservoir-Pegel (Karkheh, Karun, Doosti)
- **Iran-Rial**: yfinance + TGJU.org/bonbast.com für Bazar-Rate (multi-rate-System!)
- **GeoEPR-ETH** (Khuzestan-Araber, Aserbaidschaner am Urmia, Belutschen Sistan)
- **AidData GCDF v3.0** für chinesische Hydro-Infrastrukturprojekte
- **ACLED**: Wasser-bezogene Proteste/Konflikte als Outcome-Variable

### Spieltheoretische Methodenliteratur
- **Madani 2010** *Game Theory and Water Resources* (J. Hydrology) — perfekter methodischer Rahmen
- **Sadoff & Grey 2002** Benefit-Sharing Framework (4 Kategorien)
- **Wolf et al. TFDD** — empirisches Konfliktrisiko
- Implementierung: **Cooperative Game / Shapley Value** für faire Allokation, **Stackelberg** für Upstream-Asymmetrie, **Repeated-Game mit Issue-Linkage** (Wasser↔Flüchtlinge↔Diesel), **3-Player-Bargaining** in `nashpy`/`gambit`
- **Cross-Validation**: Vergleich mit Nile (Ägypten/GERD), Mekong, Indus

### ML / Statistik
- Prophet + XGBoost GRACE-TWS-Forecast (analog *Nature SciRep* 2025)
- Mann-Kendall + Pettitt-Test, Emerging Hot-Spot-Analysis
- Causal Impact auf Iran-Rial bei Hydro-Events (Hamoun-Dürre 2018, 2021)
- GWR/MGWR für räumliche Heterogenität
- Spatial Bayesian Networks (`pgmpy`): Wasserstress → Migration → Konflikt
- VAR/SVAR Iran-Rial × Brent × Wasserstress × Sanctions

### Mehrwert Abos
- WSJ/FT Iran-Macro-Coverage für Sanctions-Severity-Index
- FT Energy Editor für Iran Crude Export-Tracking
- Substantiell, aber weniger zentral als bei Hormuz

---

## Idee 3 — Leipzig Real Estate Quantitative Investment Engine

### Konzept-Reframing
Reine Investor-Perspektive — keine sozialräumliche Kritik. Forschungsfragen:
- Welcher Submarkt liefert beste **risikoadjustierte Total Return** = Mietrendite + Capital Appreciation − Capex − CO2-Stranded-Asset-Risiko?
- Wie groß ist **Submarket-Beta zur ECB-Rate**?
- Welche Quartiere stehen im Frühstadium der Gentrifizierung? (**Bayesian Change-Point Detection** auf Bodenrichtwerten 2010–2024)
- Welche Energieklassen werden durch **EU-CO2-Pricing 2027/2030** zum Stranded Asset?

### Datenquellen — live oder periodisch
- **Bundesbank Statistics API** (BBKRT, Residential PPI monatlich)
- **ECB Data Portal API** via SDMX (kostenfrei): MIR, HPI Residential, Bank Lending Survey
- **Europace EPX Index** monatlich für Sachsen
- **Stadt Leipzig Open Data**: Bodenrichtwerte 2010–2024, Geodaten, Bevölkerung
- **Geoportal Sachsen 3D-LoD2** für Gebäudemorphologie
- **Zensus 2022 100m**: Eigentümerquote, Leerstand, Heizungsenergieträger
- **MDV GTFS** für ÖPNV-Erreichbarkeit
- **RWI-GEO-RED Campus File** (FDZ Ruhr, Antrag SOFORT, 2–4 Wo Bearbeitung) — der Engpass

### Quant-Methodik
- Hedonic OLS → Random Forest → **XGBoost/LightGBM** (Cohen & Schaffner 2019)
- **GWR/MGWR** (Oshan et al. 2019, `mgwr`)
- Spatial Lag/Error (`pysal/spreg`)
- **SHAP** für Erklärbarkeit
- **Bayesian Change-Point Detection** (`ruptures`, PELT) auf Bodenrichtwerten → Gentrifizierungs-Early-Warning
- **Markowitz Portfolio Optimization** (`PyPortfolioOpt`) auf Submärkten
- **DCF**: NPV, IRR, Cap Rate pro Inserat
- **Stranded-Asset-Stress-Test**: CO2-Pricing-Szenarien × Energieklasse

### Mehrwert Abos — schwach
Substantiell nur für ECB-Forward-Guidance + Vonovia/LEG-REIT-Coverage. **Wenn Abos zentral genutzt werden sollen, ist dies nicht die richtige Idee.**

---

## Empfehlungs-Matrix (Quant/Game-Theory-Lens)

| Kriterium | Hormuz | Wasser | Leipzig RE |
|-----------|:------:|:------:|:----------:|
| Live-Datenfülle | ★★★★★ | ★★★★ | ★★★ |
| Spieltheoretische Tiefe | ★★★★★ | ★★★★★ | ★★ |
| Quant/ML-Tiefe | ★★★★ | ★★★★ | ★★★★★ |
| **Mehrwert WSJ/FT/Barron's** | ★★★★★ | ★★★ | ★★ |
| Aktualität / Wow-Faktor | ★★★★★ | ★★★ | ★★ |
| Machbarkeit 4 Wochen | ★★★★ | ★★★ | ★★★★★ |
| Methodische Originalität | ★★★★★ | ★★★★ | ★★★ |
| Visuelle Eindruckskraft | ★★★★★ | ★★★★ | ★★★ |

## Klare Empfehlung

**→ Idee 1 Hormuz** — und mit Abstand. Die laufende Krise ist ein **außergewöhnliches Naturexperiment für Strategic Bargaining** mit live messbarem Belief-Update (AWRP-Sprung 0.05% → 2.5% in Wochen), spieltheoretischer Kern akademisch sauber (Schelling/Powell/Fearon), Datenlage erlaubt Live-Dashboard *und* deep ML, **Abos zahlen sich konkret aus** — die AWRP-Premium-Time-Series wäre ein eigenständiger Datenbeitrag.

**Konkrete nächste Schritte**:
1. **Heute**: GFW-Forschungsregistrierung beantragen (1–3 Tage), FT-API-Key generieren (Minuten), yfinance-Brent-Test
2. **Diese Woche**: Streamlit-Skeleton + erste Pipeline (Brent + GDELT + ACLED-Tanker-Attacks)
3. **Parallel**: AWRP-Premium-Korpus aus letzten 90 Tagen FT/WSJ/Barron's/Platts manuell anfangen — der zeitintensivste Single-Step
4. **Mit Dozent abstimmen**: Critical-Geopolitics-Rahmen klären, damit Quant-Setup CSH-modulpassung-zertifiziert ist

## Kern-Literatur
- Schelling, T.C. (1960): *The Strategy of Conflict*. Harvard UP
- Powell, R. (2002): "Bargaining Theory and International Conflict", *Annual Review of Political Science* 5
- Fearon, J. (1995): "Rationalist Explanations for War", *International Organization* 49(3)
- Madani, K. (2010): "Game Theory and Water Resources", *Journal of Hydrology* 381
- Mitchell, T. (2011): *Carbon Democracy*. Verso
- Bridge, G. & Le Billon, P. (2017): *Oil*. Polity
- Yergin, D. (2020): *The New Map*. Penguin
- MacKinlay, A.C. (1997): "Event Studies in Economics and Finance", *JEL* 35
- Brodersen et al. (2015): Bayesian causal impact, *Annals of Applied Statistics* 9

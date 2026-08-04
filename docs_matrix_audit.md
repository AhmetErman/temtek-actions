# products.json technology-matrix audit

Audited against brand product pages and reputable UK/EU retailers, August 2026.
Only cells believed **wrong** or **unconfirmed-and-risky** are listed. EPREL spec values were
taken as authoritative and not questioned.

## Headline: the errors are systematic, not random

`build_products.py` defines `TECH_FACTS` keyed by **`(category, brand)`**, never by model:

```python
TECH_FACTS = {
    ("washer-dryer", "Samsung"): {"ai": "yes", "autodose": "yes"},
    ...
}
```

Every tech claim is therefore a *brand-range* assertion stamped onto whichever specific SKU was
picked from EPREL. Where a brand's picks span a flagship and a budget model (Samsung, LG and Haier
each appear twice in washer-dryers), the flagship's features leak onto the budget model. That is
the single largest source of false positives below, and it will keep producing them as models are
swapped.

## Findings

| category | brand | model | tech key | current | suggested | confidence | evidence |
|---|---|---|---|---|---|---|---|
| washer-dryer | Samsung | WD10HG6U34BB | autodose | yes | **no** | high | Samsung UK spec table for this SKU reads "Auto Dispense: No". Auto Dispense belongs to the sibling WD10HG6**U94**BE (slug `…flex-auto-dispense-system…`); the U34 slug has no such feature. https://www.samsung.com/uk/washers-and-dryers/washer-dryer-combo/wd6000f-wd10hg6u34bbu2-front-loading-ai-ecobubble-ai-energy-mode-ai-control-10kg-plus-6kg-white-wd10hg6u34beu1/ |
| dryer | Bosch | WQB246D41 | steam | yes | **no** | high | Bosch's own feature string for this exact SKU is "Silent Dry, Quick Dry Wash, Auto Dry, Self-Cleaning Condenser, Drum Interior Lighting, Home Connect" — no steam / no Iron Assist. Steam is a Bosch *washer* feature (WGB256A2GB), inherited here via the brand-level `TECH_FACTS`. https://www.amazon.de/-/en/Bosch-WQB246D41-Heat-Dryer-Silent/dp/B0FCSJQLBP , https://www.hifi.lu/en/p/11006773-bosch-heat-pump-dryer-series-8-wqb246d41 |
| washing-machine | AEG | LFR95146SUC 914505611 | autodose | yes | **no** | medium-high | AEG's 9000 AbsoluteCare feature set is SoftWater + PowerCare + Steam Refresh + AEGConnected; AutoDose is not listed on the model page or at any retailer. AEG's AutoDose line is the **8000 series** (e.g. L8FEC966CA, marketed as "AEG AutoDose 8000 Series"). Note the Electrolux twin EW9F5417SWCE (identical EPREL EEI 20.6 / 20 kWh) genuinely *is* an AutoDose model — the claim looks copied across the platform twins. https://www.appliancesuperstore.co.uk/aeg-lfr95146ws-10kg-1400rpm-freestanding-washing-machine/ |
| washing-machine | AEG | LFR95146SUC 914505611 | ai | yes | **no** (or partial) | medium | Same page: no AI/artificial-intelligence branding anywhere. AEG markets ProSense load sensing, not AI. |
| dishwasher | Bosch | SBD6ECX21E | zeolith | partial | **no** | medium-high | Bosch encodes the drying system in the model number: Zeolith/PerfectDry models carry a **Z** (SMS6**Z**CW10G, SBV6**Z**CX00E). This is SBD6**E**CX21E. No retailer listing (Galaxus, Smartech, Greatecno) mentions PerfectDry or Zeolith; EEI 31.9 / 54 kWh is also mid-pack for class A rather than PerfectDry-grade. |
| washing-machine | Beko | B5W5941BDG 457100046100 | recycled | yes | **no** / unknown | medium | Beko's own product page for this SKU lists EnergySpin, Autodose, IronFast, SteamCure, AddXtra — **no RecycledTub®**. Beko puts "RecycledTub®" in the product *title* of the models that have it (WEX840530, WEC840522, WEX940530, WER860541); this one is titled "EnergySpin and Autodose". https://www.beko.co.uk/appliances/laundry/washing-machines/product/freestanding-9kg-1400rpm-washing-machine-energyspin-autodose-b5w5941bd-graphite-white |
| washing-machine | Beko | B5W5941BDG 457100046100 | microplastic | partial | **no** | medium | Same page: no FiberCatcher / MicroFiber / microplastic filter of any kind. Nothing supports even a hedged "partial". |
| dishwasher | Beko | BDIN38560WPF 7675093877 | ai | yes | **no** | medium | Beko's 15-place AutoDose dishwashers are marketed on ProSmart Inverter, AutoDose, CornerIntense, HygieneShield, TrayWash, Quick&Shine, HomeWhiz. No AI branding on any Beko dishwasher listing found. (`autodose: yes` for this model is well supported and is not disputed.) |
| dryer | Hisense | DH5I104BBAB | ai | yes | **partial** / no | medium | The 5i "Power Steam" dryer's intelligence claims are "Smart Link" (auto-selects a programme from the paired washer) and ConnectLife energy monitoring — automation, not advertised AI. `steam`, `wifi`, `heatpump` for this model all check out. https://www.quietmark.com/products/certified-products/quiet-laundry/tumble-dryers/hisense-power-steam-5i-series-dh5i104bbab-black-heat-pump-tumble-dryer |
| washer-dryer | Whirlpool | BWT 106A3C BC | heatpump | partial | **unknown** | medium | Value is *purely* class-derived (`eprel_scraper.drying_tech_from_class` returns "Heat Pump (likely)" for any class C). No Whirlpool source anywhere confirms a heat-pump washer-dryer under this code; the range label "6th Sense heat-pump" in products.json is an assertion with no source behind it. |
| washer-dryer | Beko | B7DFT61041W 457000020300 | heatpump | partial | **unknown** | medium | Same class-C inference, same absence of evidence. No Beko heat-pump *washer-dryer* could be found in EU retail (Beko's heat pumps are standalone dryers: BM3T3713, DTIKP71131). Range label "AutoDose heat-pump" is unsourced. Note both these rows carry byte-identical EPREL figures (EEI 54.9 / 252 kWh), i.e. the same OEM platform — whatever the answer, it is the same for both. |
| dryer | Bosch | WQB246D41 | reverse | yes | unknown | low | Reversing drum action is not named in any listing for this SKU. Plausible (standard on Bosch drums) but unevidenced. |
| washing-machine | Bosch | WGB256A2GB | additem | no | possibly **yes** | low-medium | Bosch markets pause-and-add-laundry on much of the WG range; no listing for this SKU explicitly denies or confirms it. Currently an unsourced hard "no". |
| washing-machine | Electrolux | EW9F5417SWCE 914475615 | ai | yes | partial | low | Electrolux's AI claim attaches to **SensorWash** (49-stain detection). Confirmed as a brand technology, not confirmed as present on this SKU. `autodose: yes` and `steam: yes` for this model are sound. |
| dishwasher | Samsung | DW80H77H3B0 | autoopen, thirdrack | yes, yes | unverified | low | Both features are real on Samsung Bespoke dishwashers, but every source found is the North-American DW90F89P0US / DW80R9950 line. Could not confirm against an EU listing for DW80H77H3B0. |

### False negatives (currently `no` / `unknown`, should be positive)

| category | brand | model | tech key | current | suggested | confidence | evidence |
|---|---|---|---|---|---|---|---|
| washing-machine | LG | F4X9009TBC | additem | partial | **yes** | high | The repo's own `tech_evidence.json` quotes LG's spec table verbatim: `"... Add Item Yes ezDispense No ..."`. Unambiguous yes. |
| washing-machine | Beko | B5W5941BDG 457100046100 | additem | unknown | **yes** | high | Beko's own page names **AddXtra** — mid-cycle garment addition. |
| washer-dryer | Samsung | WD10HG6U34BB | steam | unknown | **yes** | high | Samsung UK page: "Hygiene Steam ... removes grime and 99.9% of certain bacteria." |
| washing-machine | Samsung | WF90F09C4S | directdrive | unknown | **no** | high | Samsung UK spec table lists motor as **DIT** (Digital Inverter Technology) — a belt-driven brushless motor, not direct drive. |
| dryer | Bosch | WQB246D41 | wifi | unknown | **yes** | high | Home Connect is named in every listing for this SKU. |
| washer-dryer | Samsung | WD18DB8995BZ | microplastic | unknown | **partial** | medium | Samsung UK: "A Less Microfiber Cycle reduces the release of microfibres by up to 39%" (a cycle, not a filter — hence partial, matching how the same feature is scored on WF90F09C4S). |
| washer-dryer | Samsung | WD18DB8995BZ | autodry | unknown | **yes** | medium | "AI Opti WashDry includes ... dry level sensing." |

### Confirmed correct — the brief's example was already fixed

The task flagged **LG F4X9009TBC `autodose=yes` / `microplastic=yes`**. In the current
`products.json` (HEAD `dd7dc4b`) those cells are already `autodose: "no"` and
`microplastic: "unknown"`, and `no` is the right answer — LG's own spec table for the SKU reads
**"ezDispense No"**. No change needed.

**But there is a live regression risk.** `tech_evidence.json` still records
`autodose: {"found": true, "phrase": "auto dose"}` for this model, matched out of a generic FAQ
block ("Q. How does the Auto-dosing function work?") that describes ezDispense in the abstract
rather than claiming this machine has it. `tech_matrix.py:331` applies evidence as
`verdict = "yes" if res["found"] else "no"`, so **running `python tech_matrix.py --apply` would
silently reinstate `autodose: "yes"` for LG F4X9009TBC.** Same mechanism put `microplastic:
found=true` in the evidence file from an image-alt string. Before that script is run against the
curated file, either the FAQ/alt-text regions need excluding or the keyword hits need reconciling
against the on-page spec table (which is the reliable signal — it is the source that says
"ezDispense No" and "Add Item Yes").

### Checked and found sound (not listed above)

Bosch WGB256A2GB `autodose`/`dosescan` (i-DOS is explicitly "i-DOS with Detergent Scan"),
`directdrive: no` (EcoSilence is belt-driven), `steam`; Samsung WF90F09C4S `autodose`, `ai`,
`additem`, `microplastic: partial`, `steam`; Samsung WD18DB8995BZ `heatpump`, `autodose` (Flex
Auto Dispense), `ai`; Haier HW100-B14397EU1 `directdrive` (Direct Motion, beltless), `steam`
(i-Refresh micro-vapour), `autodose: no`; Haier washer-dryer `directdrive`; Beko B5W5941BDG
`autodose`, `steam` (SteamCure), `ai: no`; AEG LFR95146SUC `steam` (Steam Refresh); AEG
LWR9506BN4 `heatpump` (AEG's own NL/BE pages title it "Warmtepomp"), and by platform identity
Electrolux EW9W1165RB; Whirlpool WH5IA5015BT1LS `autoopen` (NaturalDry auto door opening) and
`thirdrack` (MaxiSpace); Hisense DH5I104BBAB `steam`/`wifi`/`heatpump`; all ten dryer `heatpump`
values and all sixteen washer-dryer `heatpump: yes|no` values, which are derived mechanically from
the EPREL energy class and are internally consistent (no class-D machine is marked heat-pump, no
A++ or better dryer is marked non-heat-pump).

No brand-implausible **zeolith** claim exists: zeolith is `partial` on the Bosch dishwasher only
(BSH, the correct brand group) and `unknown` on all nine others. The Bosch value is still likely
wrong, but for model-level reasons, not brand-level ones — see the table.

## Coverage

- **Products examined: 48 of 48** (full matrix dumped and reviewed for category-logic consistency).
- **Cells actively researched: 97 of 384.** That is every one of the 71 `yes` and 9 `partial`
  cells (all positive claims), plus 17 spot-checked `no` cells on the flagships, plus a handful of
  `unknown` cells that a fetched page happened to resolve.
- **Web verification performed on 21 products** across all four categories: LG F4X9009TBC, Bosch
  WGB256A2GB, Samsung WF90F09C4S, Beko B5W5941BDG, Haier HW100-B14397EU1, AEG LFR95146SUC,
  Electrolux EW9F5417SWCE; Samsung WD18DB8995BZ, Samsung WD10HG6U34BB, AEG LWR9506BN4,
  Electrolux EW9W1165RB, Whirlpool BWT 106A3C, Beko B7DFT61041W, Haier HWD80-BP1433637T; Bosch
  WQB246D41, Hisense DH5I104BBAB, Samsung DV90DB7845GB, LG RH9X76BM; Bosch SBD6ECX21E, Beko
  BDIN38560WPF, Whirlpool WH5IA5015BT1LS, Samsung DW80H77H3B0.
- **Not researched:** the 287 `unknown` cells as a class (they make no claim), and the Midea and
  Hisense washing-machine rows plus the LG / Hisense / AEG / Electrolux / Haier / Midea dishwasher
  rows, which are `unknown` across the board and therefore contain no falsifiable assertion. Worth
  noting only that LG DB597TXSN is labelled "TrueSteam QuadWash" in its own `range` field while
  every one of its tech cells is `unknown` — the range string is carrying claims the matrix does
  not.

## Method limits

- **HTTP 403 (blocked outright):** `bosch-home.co.uk` (the URL already registered in
  `tech_sources.json`), `greatecno.com`. Bosch findings therefore rest on retailer listings
  (Amazon.de, hifi.lu, John Lewis, Marks Electrical) and Bosch's own model-code convention.
- **Timeouts (>60 s, no response):** `aeg.co.uk`, `shop.aeg.co.uk`, `galaxus.ch`. The AEG
  conclusions rest on Appliance Superstore's full feature list plus AEG's own AutoDose landing
  page, which names the 8000 series.
- **HTTP 404:** the `samsung.com/uk` URL stored in `tech_sources.json` for WD18DB8995BZ is dead
  (the live page is under the `wd8000dk-…-wd18db8995bzt1` slug — note **T1** not **U1**). That
  entry should be corrected before the next `tech_matrix.py --scan`.
- Several EU-market SKUs (Whirlpool `BWT 106A3C BC`, Beko `B7DFT61041W`, Beko `BMM5DFO5841MDC`,
  Midea models, Samsung `DW80H77H3B0`) have essentially no web presence under their EPREL model
  strings; for these, search-snippet evidence was unobtainable and the matrix cannot currently be
  verified at model level at all.
- Where a brand page could not be fetched, findings are based on search-result snippets and
  retailer spec tables, and are marked medium or low confidence accordingly.

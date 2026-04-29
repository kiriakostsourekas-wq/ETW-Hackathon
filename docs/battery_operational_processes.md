# Battery Operational Processes

Research note created from enspired's "BESS dimensions: duration, cycles and warranty terms" plus Greece-specific storage-market sources.

## Source Links

- enspired battery dimensions article: https://www.enspired-trading.com/blog/dimensions-of-a-battery
- Greece 4.7 GW standalone BESS program: https://www.ess-news.com/2025/03/18/greece-launches-4-7-gw-utility-scale-battery-storage-program/
- First Greek BESS in DAM/IDM: https://balkangreenenergynews.com/first-battery-energy-storage-systems-enter-greek-electricity-market/
- METLEN 330 MW / 790 MWh standalone BESS: https://www.metlen.com/news/press-releases/strategic-agreement-between-metlen-and-karatzis-group-for-the-largest-standalone-energy-storage-unit-in-greece/
- METLEN 251.9 MW PV + 375 MWh hybrid project: https://www.metlen.com/news/press-releases/strategic-partnership-between-metlen-and-tsakos-group-for-one-of-greece-s-largest-hybrid-power-generation-projects/

## Operational Dimensions That Matter

For BESS operation, the asset is not only "MW and MWh." The dispatch logic must account for:

- Power rating in MW: max instantaneous charge/discharge.
- Energy capacity in MWh: stored energy volume.
- Duration in hours: energy capacity divided by power rating.
- Cycle budget: how many equivalent full cycles per day or year are allowed by warranty/economics.
- Throughput: total MWh charged/discharged, often a hidden warranty constraint.
- SoC range: preferred operating band for health and flexibility.
- SoH degradation: capacity fade caused by cycling, calendar aging, temperature, and high/low SoC operation.
- Round-trip efficiency: energy lost between charging and discharging.
- Thermal/HVAC limits: poor cooling can force idle time even when market spreads are attractive.
- Grid connection limit: may be lower than battery nameplate power.
- Market-access rules: day-ahead, intraday, balancing, ancillary services, and deviation penalties differ by country.

enspired's practical conclusion is that duration and cycles should be designed together. A two-hour battery with roughly two cycles available per day is a strong commercial design because it can stack wholesale arbitrage, FCR, aFRR, and other flexibility products without forcing the battery into constant health-damaging operation.

## Generic Dispatch Process

1. Pre-market planning
   - Forecast load, RES, weather, DAM price, intraday risk, and reserve opportunity value.
   - Decide target SoC path and reserve headroom.
   - Screen for maintenance, grid limits, thermal limits, and warranty/throughput limits.

2. Day-ahead bidding
   - Charge in low-price periods, usually high-RES or low-net-load hours.
   - Discharge in high-price periods, usually evening peaks or scarcity hours.
   - Maintain terminal SoC and minimum reserve headroom if ancillary services are possible.

3. Intraday re-optimization
   - Update schedule after forecast errors, outages, RES deviations, and price changes.
   - Reduce imbalance/deviation exposure.
   - Protect SoC for later higher-value intervals.

4. Balancing and ancillary services
   - Reserve some MW capacity for frequency or balancing products when expected value beats pure energy arbitrage.
   - Hold enough SoC to deliver both upward and downward services.
   - Track opportunity cost: reserve commitment can block energy-market arbitrage.

5. Real-time operation
   - EMS sends setpoints to PCS/inverters.
   - BMS enforces cell-level safety, voltage, temperature, current, and SoC limits.
   - Operator tracks dispatch compliance, availability, alarms, and grid constraints.

6. Settlement and performance review
   - Calculate gross revenue, degradation/throughput cost, imbalance cost, availability, and realized spread.
   - Compare actual profit against perfect-foresight and heuristic dispatch.
   - Update forecasts and cycle strategy.

## Greece-Specific Battery Direction

Greece is moving toward utility-scale, front-of-the-meter batteries, not only small behind-the-meter systems.

Current/near-term signals:

- First market entry: Greece introduced its first BESS into HEnEx day-ahead and intraday markets for delivery on April 1, 2026. The first two facilities were 16.7 MW total: Petra 7.8 MW / 15.6 MWh and Dokos 8.9 MW / 17.8 MWh. These are two-hour systems in a trial run.
- Merchant rollout: Greece's 2025 standalone program targets 4.7 GW of new utility-scale BESS, with 3.8 GW on the transmission network and 900 MW on the distribution network.
- Minimum duration: the 4.7 GW program requires at least two hours of storage duration. Up to 200 MW in the congested Peloponnese region must have four-hour duration.
- Connection class: projects above 10 MW apply to the transmission operator; projects up to 10 MW apply to the distribution operator.
- Market model: the new program is merchant and front-of-the-meter, without subsidy support, so optimization quality matters directly for bankability.
- METLEN scale: the METLEN/Karatzis standalone project is 330 MW / 790 MWh in Thessaly, equal to 2.39 hours. METLEN says it will handle construction, operation, maintenance, and energy management through M Renewables.
- Hybrid direction: METLEN/Tsakos is developing a 251.9 MW PV plant with 375 MWh storage in Central Greece, showing that Greece will also have co-located or hybrid PV-plus-storage cases.

## Greece Operating Hypothesis For The Hackathon

The core Greek operational pattern should be:

- Charge around midday when solar output is high, net load is low, curtailment risk rises, and DAM prices are low.
- Discharge into late afternoon/evening peaks when solar falls, net load rises, gas units set marginal prices more often, and DAM prices rise.
- Re-optimize intraday when RES/load forecasts miss.
- Track degradation and cycle use because more cycles increase revenue but with diminishing returns and warranty/throughput cost.
- Treat 2h as the base Greek system design, 2.39h as the METLEN-specific case, and 4h as a policy/region sensitivity for congested areas such as Peloponnese.

## Data Fields We Should Add To The Project

Battery metadata:

- `battery_id`
- `owner_or_project`
- `market_role`: standalone, hybrid, co-located, aggregator
- `connection_level`: transmission, distribution
- `location_region`
- `power_mw`
- `energy_mwh`
- `duration_h`
- `round_trip_efficiency`
- `soc_min_mwh`
- `soc_max_mwh`
- `initial_soc_mwh`
- `terminal_soc_policy`
- `max_cycles_per_day`
- `annual_throughput_limit_mwh`
- `degradation_cost_eur_per_mwh`
- `support_scheme`: merchant, CfD, grant, hybrid PPA
- `allowed_markets`: DAM, IDM, balancing, FCR, aFRR

Operational time series:

- `timestamp`
- `dam_price_eur_mwh`
- `idm_price_eur_mwh`
- `charge_mw`
- `discharge_mw`
- `soc_mwh`
- `available_charge_mw`
- `available_discharge_mw`
- `reserve_up_mw`
- `reserve_down_mw`
- `realized_dispatch_mw`
- `imbalance_mwh`
- `throughput_mwh`
- `equivalent_full_cycles`
- `availability_flag`
- `thermal_derate_flag`
- `curtailment_signal`
- `action_reason`

## Modeling Implications

For the current optimizer:

- Keep the existing 15-minute dispatch resolution.
- Add duration presets: 2h, 2.39h METLEN, 4h.
- Add an annual/daily throughput or equivalent-cycle budget.
- Add thermal availability as an optional derating multiplier.
- Add a post-dispatch degradation report, even if the degradation cost remains a sensitivity.
- Keep DAM-only optimization as the first stable path, then add intraday/balancing stacking as scenario layers.

For the UI:

- Show cycle count and throughput next to profit.
- Explain action labels using both price and system context: low price plus high RES, evening peak, reserve headroom, terminal SoC.
- Show the chosen battery duration because duration changes which price spreads the system can capture.

## Open Questions

- What exact warranty limits will Greek project owners face: daily cycles, annual throughput, SoC band, or capacity-retention guarantee?
- What deviation-cost rules will apply after trial mode ends for Greek BESS?
- Which ancillary services will be practically accessible to standalone BESS in Greece first?
- Will large merchant batteries compress Greek intraday spreads quickly once several GW connect?
- Are Greek grid-connection limits lower than battery inverter/nameplate limits in congested regions?

# 5-Minute Video Demo Script

Target length: 4:45 to 5:00. Keep the UI recording moving; do not pause on
methodology details longer than needed.

## Core Message

Greece has growing renewable generation and curtailment pressure, but limited
Greek standalone BESS operating history. Our solution uses public market,
system, and weather data to forecast DAM prices, then uses a constraint-aware
battery optimizer to produce feasible schedules. The final scarcity-aware ML
strategy beats an implementable UK naive baseline on the same Greek DAM days.

## Screen Plan

Use the local UI:

- Live Dispatch page for daily schedule and battery constraints.
- Evidence page for ML versus UK naive baseline.
- Details page only if you need to show adjustable battery parameters.

Use the animated cumulative PnL chart on the Evidence page as the main proof
visual.

## Timeline And Script

### 0:00-0:30 Intro: Why This Matters

Show either the app title or the Live Dispatch page.

Say:

> Greece is adding more renewable energy, especially solar and wind. That creates
> more hours with surplus energy, curtailment, and price volatility. Batteries are
> the natural flexibility tool: charge when renewable energy is cheap or excess,
> and discharge when the system needs energy more.

Then immediately frame the challenge:

> But Greece has very limited standalone battery operating history. So the real
> question is: can we build a credible battery strategy without rich Greek BESS
> telemetry?

### 0:30-1:10 Our Approach Under Data Scarcity

Show the Live Dispatch page and the price/action chart.

Say:

> Our answer is to separate what must be learned from what is already known. We
> learn the Greek day-ahead price curve from public signals: HEnEx DAM prices,
> IPTO load and RES forecasts, weather, and calendar structure. Then battery
> behavior is not learned from missing telemetry. It is enforced by the optimizer.

Point to the chart:

> For each delivery day, the model forecasts all 96 fifteen-minute DAM intervals.
> The optimizer then converts that forecast into charge, discharge, or idle
> actions.

### 1:10-1:55 Battery Optimizer And Adjustable Parameters

Show Battery Health chips and, if useful, the Details parameter panel.

Say:

> The battery side is fully parameterized. METLEN's 330 MW / 790 MWh project is
> our public-scale demo preset, but the operating assumptions are adjustable:
> round-trip efficiency, SoC band, initial and terminal SoC, degradation cost,
> and daily cycle cap.

Then explain why this matters:

> The optimizer respects those constraints directly. It cannot charge and
> discharge at the same time, it stays inside the SoC band, it accounts for
> efficiency losses and battery wear cost, and it returns to the required terminal
> SoC. This prevents unrealistic arbitrage schedules that would look profitable
> but damage the asset.

If changing a parameter live:

> Here we can change the cycle cap for the daily demo. This changes the live
> schedule, but it does not rewrite the 38-day research evidence.

### 1:55-2:45 ML Stack: What We Tried And What Worked

Stay on Live Dispatch or switch briefly to Evidence.

Say:

> We tested simple and nonlinear models: interval profiles, Ridge, Elastic Net,
> histogram gradient boosting, ExtraTrees, and stacking. Ridge was surprisingly
> strong because Greek intraday prices have a lot of structure from calendar,
> solar shape, load, RES, and net load. ExtraTrees had the best price MAE.

Then state the final method:

> The final model is a scarcity-aware ensemble. It combines Ridge, ExtraTrees,
> histogram boosting, and an interval profile. But instead of weighting models by
> price MAE, it weights them by recent battery capture value: which model recently
> produced better dispatch economics.

Key line:

> That is the important idea: under data scarcity, we do not claim one model is
> permanently best. We adapt the ensemble using recent public validation days and
> optimize for realized battery value.

### 2:45-3:45 Honest Backtest: ML Versus UK Naive Baseline

Switch to Evidence page. Use the cumulative PnL chart if available.

Say:

> To test this honestly, we ran a chronological walk-forward backtest. Each target
> day is trained only on prior days. The target day's price is used only after the
> schedule is chosen, for settlement.

Point to the headline cards:

> On 38 evaluated Greek DAM days, our scarcity-aware ensemble plus optimizer
> earned EUR 2.968 million. The UK naive baseline earned EUR 2.571 million. That
> is EUR 397 thousand of uplift, a 15.45 percent improvement, with a 78.9 percent
> daily win rate.

Explain the benchmark:

> The UK naive baseline is deliberately simple and implementable. It copies the
> previous day's price shape, or uses a prior-seven-day interval median fallback,
> then runs the exact same battery optimizer on Greek prices.

If cumulative chart exists:

> This path shows the cumulative PnL over the test month. The green line is our
> strategy; the gray line is the UK naive benchmark. The gap is not a single-day
> artifact; it builds across the walk-forward test.

Clarify oracle:

> We also compute an oracle, but only as an upper bound. It sees realized prices,
> so it is not our benchmark.

### 3:45-4:35 Future BESS Market Impact

Show Future BESS Stress Test card.

Say:

> Today, the price-taking assumption is reasonable for a first-BESS operating
> strategy. But as more batteries enter Greece, simple arbitrage spreads should
> compress. We therefore added future stress tests, informed by storage buildout
> in Greece and comparable markets such as Spain, Italy, and Great Britain.

Then state the scenario logic:

> These are not Greek price forecasts. They are spread-compression stress tests.
> In the base case, a fixed schedule loses a large share of value, but
> re-optimizing under the new spread environment partially offsets that loss.

Key strategy implication:

> So the future strategy is not static. As more BESS capacity enters, we retrain
> the forecast, rerun the optimizer, and stress-test spread compression before
> relying on today's arbitrage margins.

### 4:35-5:00 Close

Return to the Evidence headline or Live Dispatch page.

Say:

> Our contribution is an end-to-end battery optimization framework for a market
> with scarce battery telemetry: public-data price forecasting, adjustable
> battery constraints, feasible MILP dispatch, honest comparison against an
> implementable baseline, and future stress testing as BESS penetration grows.

Final sentence:

> The result is not just a price forecast. It is a battery operating strategy
> that is feasible today and designed to adapt as the Greek storage market
> matures.

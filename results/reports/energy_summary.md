# Energy-Aware Kubernetes Scheduling: Experiment Summary

Report generated: 2026-10-20T14:08:42+05:00

Historical and experiment energy records found: 20.

## 1. Historical CodeCarbon records

The table below retains all energy records discovered in `results/raw`. These records include older exploratory runs and newer controlled runs; they should not all be treated as one homogeneous experiment.

| Source file | Duration (s) | Energy (kWh) | CPU util. (%) | Tracking mode |
|---|---|---|---|---|
| baseline_20261017_215356.csv | 60.77969136599995 | 0.00026440409042874943 | 1.694915254237288 | machine |
| baseline_20261017_223313.csv | 60.88522207400001 | 0.0003612924239709555 | 0.0 | machine |
| baseline_20261017_234505.csv | 60.428556333000415 | 0.0004636689248950925 | 1.694915254237288 | machine |
| baseline_20261018_000018.csv | 60.776690316000895 | 0.0004262668410290979 | 3.389830508474576 | machine |
| cpu_loaded_20261017_220107.csv | 60.90984348300003 | 0.0004808017930997096 | 2.542372881355932 | machine |
| cpu_loaded_20261017_223924.csv | 61.07274390600014 | 0.00045591570031063575 | 6.779661016949152 | machine |
| cpu_loaded_20261017_235523.csv | 60.46468934600034 | 0.0004026521989472816 | 5.2631578947368425 | machine |
| cpu_loaded_20261018_000208.csv | 61.555735313000696 | 0.00036511293369484004 | 5.084745762711864 | machine |
| cpu_loaded_existing.csv | 60.86517222600014 | 0.0003952324365636687 | 6.779661016949152 | machine |
| emissions_existing.csv | 61.235862606999945 | 0.00030524025990633243 | 1.694915254237288 | machine |
| emissions_existing.csv | 62.08554616899983 | 0.00036741534006865087 | 8.333333333333334 | machine |
| emissions_existing.csv | 60.29194517999986 | 0.0002356090867726707 | 3.4482758620689653 | machine |
| energy_baseline_01_20261019_183823_121210.csv | 61.70780466100041 | 0.0002248814500178554 | 3.389830508474576 | machine |
| energy_baseline_02_20261019_194111_784503.csv | 61.67713826200088 | 0.0002356579952094802 | 3.389830508474576 | machine |
| energy_baseline_03_20261019_195934_496437.csv | 62.19615049700042 | 0.00022788244007517365 | 3.389830508474576 | machine |
| energy_loaded_01_20261019_192553_233951.csv | 62.862428403001104 | 0.00039461365542982146 | 6.779661016949152 | machine |
| energy_loaded_02_20261019_194734_735859.csv | 63.33102727400001 | 0.00039169575889509494 | 3.389830508474576 | machine |
| energy_loaded_03_20261019_200124_297053.csv | 60.34196326200072 | 0.0003553532375784855 | 5.084745762711864 | machine |
| energy_loaded_03_repeat_20261019_200654_935427.csv | 61.23535564699887 | 0.00036396688230560994 | 0.0 | machine |
| energy_pipeline_smoke_loaded_20261019_175829_427620.csv | 30.93612837099954 | 0.00018314504253216392 | 3.4482758620689653 | machine |

## 2. Controlled CPU workload experiment

Pair 1 compares `baseline_01` with `loaded_01`; pair 2 compares `baseline_02` with `loaded_02`; pair 3 compares `baseline_03` with `loaded_03_repeat`. The original `loaded_03` is excluded from paired analysis because it had incomplete CPU-test pod sampling, but its raw files are preserved.

| Pair | Baseline energy (kWh) | Loaded energy (kWh) | Energy change | Baseline node CPU | Loaded node CPU | Loaded pod samples | Loaded pod avg CPU (cores) |
|---|---|---|---|---|---|---|---|
| 1 | 0.000224881 | 0.000394614 | +75.5% | 60.7% | 55.8% | 10 | 0.613 |
| 2 | 0.000235658 | 0.000391696 | +66.2% | 37.6% | 61.0% | 10 | 0.772 |
| 3 | 0.000227882 | 0.000363967 | +59.7% | 39.2% | 59.4% | 11 | 0.834 |

- Mean baseline energy estimate: **0.000229474 kWh**
- Mean loaded energy estimate: **0.000383425 kWh**
- Change between means: **+67.1%**

## 3. Scheduler simulation

The scheduler benchmark uses illustrative CPU and power inputs. It compares a first-feasible-node baseline with the lowest-score feasible-node policy. It is a simulation, not a live Kubernetes scheduler integration or a measurement of energy savings.

| Scenario | Baseline node | Energy-aware node | Baseline score | Energy-aware score | Baseline gap from best |
|---|---|---|---|---|---|
| scenario_01 | node-a | node-b | 0.71 | 0.33 | 0.38 |
| scenario_02 | node-b | node-c | 0.57 | 0.38 | 0.19 |
| scenario_03 | node-a | node-a | 0.3 | 0.3 | 0.0 |
| scenario_04 | node-a | node-b | 0.5 | 0.37 | 0.13 |
| scenario_05 | node-b | node-c | 0.49 | 0.41 | 0.08 |
| scenario_06 | node-a | node-b | 0.66 | 0.41 | 0.25 |

- Scenarios compared: **6**
- Scenarios with a different selected node: **5**
- Mean baseline score gap from best feasible score: **0.1717**

## 4. Methodological limitations

- CodeCarbon reports machine-level energy estimates, not direct per-pod energy.
- Hardware RAPL energy counters were unavailable in this VM; CPU energy is estimated.
- Background VM activity and run-to-run variation may affect results.
- The original `loaded_03` had incomplete pod sampling; `loaded_03_repeat` is used for pair 3.
- Minikube currently has one node, so real multi-node scheduler behavior has not been evaluated.
- Scheduler benchmark power values are illustrative and must not be presented as measured power.
- The baseline in the simulation is first-feasible-node selection, not Kubernetes' complete default scheduler.

## 5. Next steps

1. Incorporate workload characteristics and node feasibility into the policy.
2. Define a fair multi-node evaluation or a clearly labelled simulation protocol.
3. Evaluate scheduling decisions and performance separately from machine-level energy estimates.
4. Keep all raw measurements and report generation reproducible.

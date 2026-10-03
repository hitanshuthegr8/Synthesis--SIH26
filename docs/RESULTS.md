# Phase 1.5 Results (Demo)

Results below describe **deterministic demo verification**, not operational forecast verification.

## Heavy rain scenario (24h tp24, Maharashtra demo point)

- Source inputs (mm): ECMWF 48, GFS 21, AI 57, GEFS 29  
- Regime: HEAVY_RAIN with EXTREME disagreement  
- Blended value: computed by backend weighted average (not hardcoded in UI)  
- Weights: adaptive inverse-skill + contextual adjustment  

## Model failure scenario

- GFS forced anomalous (5 mm vs ~48–57 mm peers)  
- GFS weight decreases; remaining weights renormalize  
- Blend and uncertainty change measurably vs heavy rain baseline  

## Test evidence

- 168+ automated backend tests including property invariants, leakage guard, regression cycle, and API integration  
- Frontend guard: no hardcoded MAE/weight/uncertainty literals  

Re-run locally:

```bash
make test
```

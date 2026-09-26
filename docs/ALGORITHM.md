# SYNTHESIS Phase 1.5 Algorithm

## Pipeline order

1. Ingest demo source adapters  
2. Validate and normalize to canonical grid/units  
3. Load historical skill (inverse-error priors)  
4. Classify weather regime (rule engine)  
5. Measure model disagreement  
6. Adaptive weighting (skill + regime + lead + disagreement adjustment)  
7. Weighted deterministic blend  
8. Uncertainty range (historical error + spread + availability)  
9. Structured explanation (no LLM)  
10. Verification and autopsy when observations exist  

## Weighting

Phase 1.5 combines historical MAE-based trust with contextual adjustments. Weights are normalized to sum to 1 with a minimum floor.

## Precipitation

Weighted deterministic blending is used when quantile inputs are unavailable. The API remains ready for quantile-aware blending in Phase 2.

## Uncertainty

Outputs are labelled **Forecast uncertainty range**, not calibrated confidence intervals.

## Baselines

Climatology, persistence, best single model, and simple mean are supported in the verification/backtest layer for value comparison.

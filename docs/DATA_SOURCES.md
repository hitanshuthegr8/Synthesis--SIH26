# Data Sources (Phase 1.5)

## Logical sources

| Source ID | Phase 1.5 implementation |
| --- | --- |
| `ecmwf` | `DemoECMWFSource` — synthetic JSONL adapter |
| `gfs` | `DemoGFSSource` |
| `gefs` | `DemoGEFSSource` |
| `ai` | `DemoAISource` |

All adapters implement the same `ForecastSource` contract and return canonical forecast records.

## Demo archives

Generated under `data/demo/` with `MANIFEST.json` (dataset version, seed, file hashes).

## Live sources (deferred)

Real ECMWF/GFS/GEFS/API adapters replace demo adapters without changing the pipeline interface. The UI must continue to distinguish demo versus operational data.

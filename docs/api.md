# API Documentation

Base URL: `http://localhost:8000`

## GET /api/health
Check system status.
Response:
```json
{
  "status": "ok"
}
```

## GET /api/models
List available forecast models.
Response:
```json
[
  {
    "id": "gfs",
    "name": "GFS"
  }
]
```

## GET /api/forecasts
Retrieve forecasts for a given location and time.
Response:
```json
{
  "data": []
}
```

## GET /api/forecast/grid
Report whether a repository-backed spatial forecast grid is available. The
current repository contains point/demo forecasts only, so this endpoint
returns `UNAVAILABLE` and never returns fabricated values.

Response:
```json
{
  "status": "UNAVAILABLE",
  "variable": "temperature",
  "lead_hours": 24,
  "grid_spec": {
    "south": 5.0,
    "north": 40.0,
    "west": 65.0,
    "east": 100.0,
    "resolution": 0.25,
    "latitude_count": 141,
    "longitude_count": 141
  },
  "values": null
}
```

When `GFS_ENABLED=true`, this endpoint invokes the optional NOAA GFS provider.
Requests may specify `source=GFS`, `model=GFS`, `variable=temperature`,
`lead_hours` from 0 through 168, and an optional ISO-8601
`initialization` (the provider supports 00Z initialization). For example:

`GET /api/forecast/grid?source=GFS&model=GFS&variable=temperature&lead_hours=24&initialization=2026-09-25T00:00:00Z`

On success, the response includes the validated 141x141 field and provenance
for the source product, source and normalized units, native and target
resolution, target domain, coordinate normalization, direct-subset
transformation, and cache/retrieval details. `AVAILABLE` is returned only
after retrieval, GRIB decoding, variable/unit checks, coordinate and value
validation, and target-grid validation all succeed.
The provider requires the GRIB2 decoder dependencies from
[`backend/requirements.txt`](../backend/requirements.txt). Without a valid
retrieved and decoded product, the endpoint remains `UNAVAILABLE`.

GFS configuration is environment-driven:

- `GFS_ENABLED` (default `false`)
- `GFS_BASE_URL`
- `GFS_CYCLE` (the MVP resolver currently supports 00Z only)
- `GFS_CACHE_DIR`
- `GFS_REQUEST_TIMEOUT_SECONDS`
- `GFS_MAX_DOWNLOAD_BYTES`

ECMWF IFS temperature is also available behind explicit configuration:

- `ECMWF_ENABLED` (default `false`)
- `ECMWF_BASE_URL`
- `ECMWF_CACHE_DIR`
- `ECMWF_REQUEST_TIMEOUT_SECONDS`

Use `source=ECMWF`, `model=IFS`, and an ISO-8601 `initialization` to request
the official 00Z IFS `oper/fc` 0.25-degree GRIB2 product. The provider reads
the `.index` file and retrieves only the selected `2t` GRIB message using an
HTTP byte range. Precipitation and ENS are not implemented.

## GET /api/forecast/grid/blend

Request an explicit equal-weight SYNTHESIS blend of the real GFS and ECMWF
temperature fields:

`GET /api/forecast/grid/blend?variable=temperature&lead_hours=24&initialization=2026-09-25T00:00:00Z`

Both providers must retrieve and validate the same initialization, lead,
variable, units, and target grid. The response uses the existing spatial
forecast representation and records `source=SYNTHESIS`, `model=SYNTHESIS`,
`blend_method=weighted mean`, and `source_weights` of 0.5 for GFS and ECMWF.
If either provider is unavailable or mismatched, the endpoint returns
`UNAVAILABLE`; it never falls back to one source or demo data.

## POST /api/forecast/verification/spatial

The spatial verification endpoint currently reports `UNAVAILABLE` because no
real observation/truth provider is configured. It does not generate synthetic
truth data. The verification engine supports MAE, RMSE, bias, valid/invalid
cell counts, and an explicit per-cell absolute error field once an explicitly
supplied truth field is available. These are deterministic verification
metrics, not confidence scores, and are not used to generate weights.

ERA5 is the configured reference/reanalysis path for real verification. The
forecast initialization plus lead is converted to a UTC valid time, and ERA5
2m temperature is normalized from Kelvin to Celsius on the exact target grid.
ERA5 remains disabled by default (`ERA5_ENABLED=false`) and requires
`ERA5_CDS_KEY`; production never uses synthetic truth.
The offline test suite never contacts CDS. To run the explicit live validation,
set `RUN_ERA5_LIVE=1` together with `ERA5_CDS_KEY` and run
`python -m pytest backend/tests/integration/test_era5_live.py -q`. The provider
reuses the deterministic ERA5 cache for repeated valid-time requests and
returns `UNAVAILABLE` for disabled, unconfigured, failed, or incompatible
retrievals.

## POST /api/blend
Trigger a new blend operation.
Request:
```json
{
  "lat": 40.7,
  "lon": -74.0,
  "time": "2023-10-01T12:00:00Z"
}
```
Response:
```json
{
  "blend_id": "12345",
  "result": {}
}
```

## GET /api/reliability/map
Get spatial reliability data.
Response:
```json
{
  "regions": []
}
```

## GET /api/reliability/model/{model_id}
Get reliability stats for a specific model.
Response:
```json
{
  "model_id": "gfs",
  "rmse": 2.1
}
```

## GET /api/verification
Get system verification metrics.
Response:
```json
{
  "metrics": []
}
```

## GET /api/autopsy/{run_id}
Get explanation data for a specific forecast run.
Response:
```json
{
  "run_id": "12345",
  "explanations": []
}
```

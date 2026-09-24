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

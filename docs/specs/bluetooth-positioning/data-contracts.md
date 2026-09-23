# Data Contracts

## Versioning
External payloads carry schema_version (initial 1.0). Compatible minor additions may be ignored; unknown majors are rejected/quarantined.

## Anchor
```json
{"anchor_id":"anchor-a1","serial_number":"SN-A1-0042","scene_id":"scene-123","state":"active","position":{"x_m":2.2,"y_m":3.1,"z_m":3.2},"orientation":{"yaw_deg":0,"pitch_deg":0,"roll_deg":0},"capabilities":["channel_sounding"],"provider_id":"gateway-west","provider_device_id":"vendor-stable-id","revision":3}
```

## Tag
```json
{"tag_id":"tag-00421","serial_number":"TAG-00421","state":"active","capabilities":["channel_sounding","battery_service"],"provider_id":"gateway-west","provider_device_id":"vendor-tag-id","battery":{"percent":74,"voltage_v":null,"status":"normal","source":"gatt_battery_service","observed_at":"2026-09-24T00:00:00Z"},"last_seen_at":"2026-09-24T00:00:01Z","revision":7}
```

## Assignment
```json
{"assignment_id":"assign-uuid","tag_id":"tag-00421","entity_type":"asset","entity_id":"forklift-27","display_name":"Forklift 27","valid_from":"2026-09-24T00:00:00Z","valid_to":null,"reason":"commissioning","created_by":"principal-id"}
```

## Range observation
Topic: `scenescape/data/bluetooth/range/{scene_id}/{anchor_id}/{tag_id}`
```json
{"schema_version":"1.0","provider_id":"gateway-west","session_id":"cs-9af0","sequence":48124,"source_timestamp":"2026-09-24T00:00:01.120Z","method":"channel_sounding","distance_m":8.431,"distance_stddev_m":0.12,"rssi_dbm":-61,"azimuth_deg":null,"elevation_deg":null,"nlos_probability":0.08,"quality":0.93,"provider_details":{}}
```

## Tracked position
Topic: `scenescape/data/bluetooth/position/{scene_id}/{tag_id}`
```json
{"schema_version":"1.0","source_timestamp":"2026-09-24T00:00:01.150Z","tag_id":"tag-00421","scene_id":"scene-123","position":{"x_m":12.42,"y_m":8.17,"z_m":1.05},"velocity":{"vx_mps":0.41,"vy_mps":-0.17,"vz_mps":0.0},"quality":{"state":"good","horizontal_uncertainty_m":0.31,"vertical_uncertainty_m":null,"score":0.94,"anchors_visible":6,"anchors_used":5,"residual_rms_m":0.15,"gdop":1.7,"method":"channel_sounding"},"solver":{"name":"robust-wls","version":"1"},"tracker":{"name":"cv-kalman","version":"1","predicted":false}}
```

## Baseline API
```text
GET/POST   /api/v2/bluetooth/anchors
GET/PATCH  /api/v2/bluetooth/anchors/{anchor_id}
POST       /api/v2/bluetooth/anchors/{anchor_id}/activate|deactivate
GET/POST   /api/v2/bluetooth/tags
GET/PATCH  /api/v2/bluetooth/tags/{tag_id}
POST       /api/v2/bluetooth/tags/{tag_id}/activate|deactivate
GET/POST   /api/v2/bluetooth/assignments
POST       /api/v2/bluetooth/assignments/{id}/close
GET/POST   /api/v2/bluetooth/calibrations
GET        /api/v2/bluetooth/diagnostics
GET        /api/v2/bluetooth/tags/{tag_id}/positions
POST       /api/v2/bluetooth/measurements  # service-auth only
```

## Scene live projection
```json
{"id":"bt:tag-00421","category":"forklift","translation":[12.42,8.17,1.05],"velocity":[0.41,-0.17,0],"source":"bluetooth","positioning":{"tag_id":"tag-00421","method":"channel_sounding","state":"good","horizontal_uncertainty_m":0.31,"anchors_used":5,"observed_at":"2026-09-24T00:00:01.150Z"}}
```

## Validation
Finite numeric values only; distance >= 0 and <= site max; quality/probability in [0,1]; battery [0,100] and null means unknown; source timestamp inside configured replay window; bounded provider_details; duplicate handling by provider/session/sequence; bounded normalized IDs.

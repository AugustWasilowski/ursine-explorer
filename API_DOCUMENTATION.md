# ADS-B HTTP API Documentation

## Overview

The enhanced ADS-B HTTP API provides access to aircraft data, system status, and diagnostics with improved error handling, rate limiting, and comprehensive logging.

## Base URL

```
http://localhost:8080
```

## Rate Limiting

- **Limit**: 120 requests per minute per IP address
- **Headers**: Rate limit information is included in response headers:
  - `X-RateLimit-Limit`: Maximum requests per window
  - `X-RateLimit-Remaining`: Remaining requests in current window
  - `X-RateLimit-Reset`: Unix timestamp when limit resets

## Authentication

Currently no authentication is required. All endpoints are publicly accessible.

## Endpoints

### Aircraft Data

#### GET /data/aircraft.json

Returns aircraft data in legacy format for backward compatibility.

**Query Parameters:**
- `format` (optional): Response format (`json`, `compact`)
- `limit` (optional): Maximum number of aircraft to return (1-1000)

**Response:**
```json
{
  "now": 1640995200.0,
  "messages": 12345,
  "aircraft": [
    {
      "hex": "A12345",
      "flight": "UAL123",
      "alt_baro": 35000,
      "gs": 450,
      "track": 270,
      "lat": 40.7128,
      "lon": -74.0060,
      "squawk": "1200",
      "category": "A3",
      "messages": 42,
      "last_seen": "2021-12-31T12:00:00",
      "is_watchlist": false
    }
  ],
  "stats": {...}
}
```

#### GET /data/aircraft_enhanced.json

Returns aircraft data with enhanced pyModeS fields.

**Query Parameters:**
- `format` (optional): Response format (`json`, `compact`)
- `limit` (optional): Maximum number of aircraft to return (1-1000)
- `include_raw` (optional): Include raw pyModeS data (`true`, `false`)

**Response:**
```json
{
  "now": 1640995200.0,
  "messages": 12345,
  "aircraft": [
    {
      "hex": "A12345",
      "flight": "UAL123",
      "alt_baro": 35000,
      "gs": 450,
      "track": 270,
      "lat": 40.7128,
      "lon": -74.0060,
      "enhanced": {
        "alt_gnss": 35100,
        "vertical_rate": 0,
        "true_airspeed": 465,
        "indicated_airspeed": 280,
        "mach_number": 0.78,
        "magnetic_heading": 268,
        "roll_angle": 2.5,
        "navigation_accuracy": {...},
        "surveillance_status": "ADS-B"
      },
      "data_sources": ["DF17", "DF18"],
      "first_seen": "2021-12-31T11:30:00",
      "last_seen": "2021-12-31T12:00:00",
      "is_watchlist": false
    }
  ],
  "enhanced_fields": {...}
}
```

### System Status

#### GET /api/health

Health check endpoint for monitoring system status.

**Response (200 OK - Healthy):**
```json
{
  "timestamp": "2021-12-31T12:00:00",
  "healthy": true,
  "status": "healthy",
  "checks": {
    "dump1090_running": {
      "status": "pass",
      "description": "dump1090 process is running"
    },
    "data_freshness": {
      "status": "pass",
      "description": "Receiving fresh aircraft data",
      "last_update": "2021-12-31T11:59:45"
    }
  },
  "uptime_seconds": 3600
}
```

**Response (503 Service Unavailable - Unhealthy):**
```json
{
  "timestamp": "2021-12-31T12:00:00",
  "healthy": false,
  "status": "unhealthy",
  "checks": {...}
}
```

#### GET /api/status

Detailed system status and diagnostics.

**Response:**
```json
{
  "timestamp": "2021-12-31T12:00:00",
  "system": {
    "dump1090_running": true,
    "meshtastic_connected": true,
    "http_server_running": true,
    "control_server_running": true
  },
  "aircraft": {
    "total_tracked": 25,
    "watchlist_count": 2,
    "with_position": 20,
    "with_velocity": 18,
    "with_altitude": 22
  },
  "watchlist": {
    "size": 5,
    "codes": ["A12345", "B67890"]
  },
  "message_sources": {...},
  "decoder": {...},
  "stats": {...}
}
```

#### GET /api/stats

Processing statistics and performance metrics.

**Query Parameters:**
- `period` (optional): Statistics period (`1m`, `5m`, `15m`, `1h`)
- `format` (optional): Response format (`json`, `compact`)

**Response:**
```json
{
  "timestamp": "2021-12-31T12:00:00",
  "uptime_seconds": 3600,
  "performance": {
    "message_rate_per_second": 125.5,
    "aircraft_update_rate": 2.3,
    "error_rate": 0.5
  },
  "memory": {
    "rss_mb": 45.2,
    "vms_mb": 120.8,
    "percent": 2.1
  },
  "counters": {...},
  "aircraft_distribution": {...}
}
```

#### GET /api/sources

Message source status and configuration.

**Response:**
```json
{
  "timestamp": "2021-12-31T12:00:00",
  "sources": {
    "dump1090": {
      "type": "dump1090",
      "running": true,
      "last_data_time": "2021-12-31T11:59:58",
      "watchdog_timeout": 60,
      "needs_restart": false,
      "config": {
        "frequency": 1090000000,
        "lna_gain": 40,
        "vga_gain": 20,
        "enable_amp": true
      }
    }
  },
  "total_sources": 1,
  "active_sources": 1
}
```

#### GET /api/decoder

pyModeS decoder performance metrics.

**Query Parameters:**
- `format` (optional): Response format (`json`, `compact`)
- `detailed` (optional): Include detailed metrics (`true`, `false`)

**Response:**
```json
{
  "timestamp": "2021-12-31T12:00:00",
  "decoder_type": "pyModeS",
  "performance": {
    "messages_processed": 12345,
    "decode_errors": 67,
    "success_rate": 99.46
  },
  "message_types": {
    "DF17": 8500,
    "DF18": 2800,
    "DF4": 1045
  },
  "position_calculations": {
    "successful": 20,
    "failed": 5
  },
  "aircraft_with_enhanced_data": {
    "true_airspeed": 15,
    "magnetic_heading": 12,
    "navigation_accuracy": 8
  }
}
```

### Legacy Endpoints

#### GET /data/fft.json

Returns FFT data for waterfall viewer (legacy compatibility).

## Error Handling

All endpoints return structured error responses:

```json
{
  "error": "Bad Request",
  "message": "Parameter 'limit' must be between 1 and 1000",
  "status_code": 400,
  "timestamp": "2021-12-31T12:00:00",
  "path": "/api/stats",
  "method": "GET",
  "request_id": "abc12345"
}
```

### HTTP Status Codes

- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters or malformed request
- `404 Not Found`: Endpoint not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: System unhealthy

## Headers

### Request Headers

- `User-Agent`: Client identification (optional but recommended)

### Response Headers

- `Content-Type`: Always `application/json`
- `Access-Control-Allow-Origin`: `*` (CORS enabled)
- `Cache-Control`: `no-cache, no-store, must-revalidate`
- `X-API-Version`: API version (currently `2.0`)
- `X-RateLimit-Limit`: Rate limit maximum
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Rate limit reset time

## Logging

The API maintains detailed access and error logs:

- **Access Log**: `api_access.log` - All successful requests
- **Error Log**: `api_errors.log` - All errors and rate limit violations

## Migration from v1.0

The enhanced API maintains backward compatibility with existing endpoints:

- `/data/aircraft.json` continues to work with legacy format
- New `/data/aircraft_enhanced.json` provides additional pyModeS fields
- All existing query parameters are supported
- Response format remains the same for legacy endpoints

## Examples

### Basic Aircraft Data

```bash
curl "http://localhost:8080/data/aircraft.json"
```

### Enhanced Aircraft Data with Limit

```bash
curl "http://localhost:8080/data/aircraft_enhanced.json?limit=10"
```

### Health Check

```bash
curl "http://localhost:8080/api/health"
```

### System Statistics

```bash
curl "http://localhost:8080/api/stats?period=5m"
```
"""Constants for CPAP Local integration."""

import secrets

DOMAIN = "cpap_local"

DEFAULT_SCAN_INTERVAL_HOUR = 10  # 10:00 AM
DEFAULT_AHI_THRESHOLD = 10.0
DEFAULT_MIN_USAGE_HOURS = 4.0

CONF_FETCH_METHOD = "fetch_method"
CONF_HTTP_URL = "http_url"
CONF_LOCAL_PATH = "local_path"
CONF_SYNC_HOUR = "sync_hour"
CONF_AHI_THRESHOLD = "ahi_threshold"
CONF_MIN_USAGE_HOURS = "min_usage_hours"
CONF_RAW_SYNC_ENABLED = "raw_sync_enabled"
CONF_RAW_SYNC_PATH = "raw_sync_path"
CONF_RAW_SYNC_SCOPE = "raw_sync_scope"

# ESP WiFi-bridge mode
CONF_FETCH_METHOD_ESP = "esp"
CONF_ESP_DEVICE_ID = "esp_device_id"  # ESPHome device ID or name
CONF_CPAP_ID = "cpap_id"  # Logical CPAP device ID (user-assigned)
CONF_ESP_INGEST_TOKEN = "esp_ingest_token"  # Bearer token the ESP uses for ingest POST

# HTTP and local methods (existing)
FETCH_METHOD_HTTP = "http"
FETCH_METHOD_LOCAL = "local"
FETCH_METHODS = [FETCH_METHOD_HTTP, FETCH_METHOD_LOCAL, CONF_FETCH_METHOD_ESP]

# Scope options
SCOPE_SUMMARY_ONLY = "summary_only"
SCOPE_LAST_7_DAYS = "last_7_days"
SCOPE_ALL_AVAILABLE = "all_available"


def generate_ingest_token() -> str:
    """Generate a secure random bearer token for ESP ingest auth."""
    return secrets.token_urlsafe(32)

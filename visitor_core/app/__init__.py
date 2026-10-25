"""visitor_core — Website Visitor Identity Capture & CRM Ingestion.

Client sites embed tracker/snippet.js -> POST /api/v1/capture/track (RudderStack-
style ingestion) -> Celery worker resolves identity:
  COOKIE_STITCH (first-party cookie / ?he= marker)
  -> LOCAL_GEOIP (embedded MaxMind MMDB corporate resolution)
  -> RETENTION_API (proxy-routed commercial fallback for unstitched residential)
  -> ANONYMOUS (graceful terminal state, traceback surfaced, never hangs)
Every step broadcasts a CRM wire-schema envelope on Redis Pub/Sub; the
dashboard subscribes via WS /api/v1/ws/crm/live.
"""
__version__ = "0.1.0"

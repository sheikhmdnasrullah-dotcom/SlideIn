# Official analytics adapters

This package contains optional adapters for client-owned, consent-aware first-party event collection. It does not replace the canonical Slidein workspace or create an acquisition workflow.

## Packages

- `@snowplow/browser-tracker`: official Snowplow browser SDK (BSD-3-Clause).
- `@rudderstack/analytics-js`: official RudderStack browser SDK. The separate `rudder-server` is Elastic License 2.0, not Apache/MIT; managed-service use requires a license review.
- `logsnag`: official JavaScript SDK for operational events. `logsnag/logsnag-python` is not a current official repository; the Python visitor service retains its narrow HTTPS adapter instead.
- `esbuild`: builds the browser adapter; generated bundles are not independent inventory entries.

## Build

```bash
npm ci --ignore-scripts
npm run build
```

Serve `dist/official-tracker.js` from the client site's own approved static origin. Initialization is deliberately manual:

```js
window.SlideinOfficialAnalytics.init({
  consent: true, // set only after the client site's consent flow
  snowplow: {
    collectorUrl: "https://collector.client.example",
    appId: "client-site",
    siteKey: "approved-site-key"
  },
  rudderstack: {
    writeKey: "public-browser-write-key",
    dataPlaneUrl: "https://events.client.example"
  }
});
window.SlideinOfficialAnalytics.trackPage();
```

Do not enable both providers merely because they are installed. Choose one event pipeline per site unless a measured need justifies both. RudderStack custom events are supported directly. Snowplow custom events require a versioned Iglu schema and are not emulated by this adapter.

## Boundaries

- No event is sent before explicit initialization with `consent: true`.
- No canvas, hardware, or browser fingerprinting exists in the official adapter.
- IP/ASN data may describe a network operator; it does not establish a person's identity or employer.
- Session-to-person stitching occurs only through explicit consented identifiers such as a form/login identity, not covert fingerprinting.
- LogSnag is for non-personal operational events, not a customer analytics dashboard.
- The old `snippet.js` is a legacy clean-room prototype, not an official Snowplow or RudderStack integration.

# Consented website lead capture

## Product boundary

A website connection is a discovery source inside the existing Slidein workspace. It is configured in **Settings**, creates the existing **Prospect** record, and uses the existing evidence and activity model. It does not add a dashboard, CRM, parallel lead type, or autonomous outreach path.

Anonymous visits cannot reliably reveal a person's email. Slidein therefore creates a website lead only after a visitor explicitly submits a valid email with consent. GeoIP/ASN data is network context, never proof of a person, employer, or email address.

## Operator and visitor flow

```text
Operator connects a client-owned HTTPS domain in Settings
  -> Slidein stores a WebsiteConnection and returns installation code
  -> Operator installs the snippet and consent-enabled form markup on that site
  -> Visitor explicitly consents to first-party page events
  -> Anonymous consented events remain unattached WebsiteEvent rows
  -> Visitor submits a form email and checks the consent box
  -> Slidein creates or reuses the canonical Prospect
  -> Prior consented events from the same website and session attach to that Prospect
  -> Research, qualification, drafting, approval, and outreach continue normally
```

Connecting a website returns `remote_deployment=False`. Slidein generates code; it does not modify or deploy to a remote website automatically.

## Canonical records

- `WebsiteConnection`: tenant, normalized public HTTPS domain, provider selection, site key, and status.
- `WebsiteEvent`: tenant, website, external event ID, session ID, event type, page URL, and optional canonical Prospect reference.
- `Prospect`: the one existing person/lead record; website identification is not a second acquisition model.
- `EvidenceItem`: records the explicit website identification, page source, collector, and verified status.

## API surface

| Route | Access | Behavior |
|---|---|---|
| `POST /v1/tenants/{tenant_id}/websites` | Authenticated operator; settings module | Validate and connect a domain; return snippet/capture URLs |
| `GET /v1/tenants/{tenant_id}/websites` | Authenticated tenant workspace; settings module | List only that tenant's connections |
| `GET /v1/public/website-snippet/{site_key}.js` | Public installation asset | Return no-store browser JavaScript for the selected write-only connection |
| `POST /v1/public/website-events/{site_key}` | Public write-only ingestion | Validate consent/origin/payload, deduplicate, capture events, and identify explicit form leads |
| `POST /v1/tenants/{tenant_id}/analytics/network-context` | Authenticated tenant workspace; settings module | Read a configured local GeoIP MMDB without network I/O |

The site key selects a write-only connection; it is not a read credential. Event page URLs must use HTTPS and belong to the connected domain or one of its subdomains. External event IDs are idempotent per website. Only `page_view`, `form_submit`, and `identify` are accepted.

## Browser behavior

The generated native snippet:

- stores only a random session identifier in `sessionStorage`;
- sends page events only when `trackPage(true)` is called after consent;
- handles forms marked `data-slidein-lead-capture` only when an email is present and `input[data-slidein-consent]` is checked;
- uses `sendBeacon` or `fetch` with credentials omitted;
- collects no canvas, hardware, or browser fingerprint;
- does not scrape email addresses from the page or visitor browser.

The official Snowplow and RudderStack browser adapter is separately built at `visitor_core/tracker/dist/official-tracker.js`. It also requires explicit initialization with `consent: true`. Those SDKs are installed, but no Snowplow collector, RudderStack data plane, or `rudder-server` is deployed by this feature. They remain unwired in the canonical registry until a configured tenant-scoped adapter and tests exist. LogSnag is restricted to non-personal operational events.

## Privacy and delivery boundaries

- Consent denial or absence is rejected by the API; an anonymous page view never creates a Prospect.
- Cookies, advertising identifiers, IP data, and browser/device fingerprints are not verified email identities. Never use them to covertly reveal, guess, harvest, or enrich an anonymous visitor's email or personal profile.
- Form/identify events require an explicitly submitted, validated email. A login, verified customer link, or other explicit consented first-party identification may establish identity only when it already has a verified identifier; it must not invent one for an unknown visitor.
- Prior-event stitching is limited to the same tenant, website, and session and only to previously consented events.
- A submitted email and consent do not authorize autonomous email sending; existing approval and sending policy still apply.
- GeoIP2 uses a local MMDB and returns network context only. It does not infer a company domain or verified employer.
- Provider failures and missing configuration must remain explicit; no synthetic identity, evidence, or success is allowed.

## Verification scope

Hermetic tests cover consent denial, anonymous events, explicit lead creation and evidence, duplicate delivery, prior-session stitching, missing identity, cross-domain rejection, and tenant isolation. Tracker checks cover build validity, no initialization without consent, and no event before initialization. A local-site walkthrough also executed the actual generated snippet in a simulated browser DOM, sent its two consented events through the in-process API, and verified one canonical Prospect, verified evidence, duplicate suppression, and two stitched events with zero external requests. These tests use no live tracking, provider, collector, DNS, scraping, or email effects.

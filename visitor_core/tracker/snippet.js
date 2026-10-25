/* Slidein visitor tracker — client embed (Snowplow-modelled, clean-room).
 *
 * Client installs:
 *   <script async src="https://<backend>/api/v1/tracker.js?site_key=SITE_KEY"></script>
 * or copy-paste with hardcoded origin:
 *   <script> ... this file with __API_ORIGIN__ replaced ... </script>
 *
 * Behaviour:
 *   - intercepts ?he=<token> (or configured marker) on ANY page load, stitches
 *     it into the first-party __sl_vid cookie immediately, then strips it from
 *     the URL bar (replaceState — no reload, no history pollution)
 *   - collects canvas/browser/hardware fingerprint vectors (Snowplow-style
 *     payload), POSTs to __API_ORIGIN__/api/v1/capture/track asynchronously
 *   - sendBeacon on pagehide for unload-time reliability
 */
(function () {
  "use strict";

  var API_ORIGIN = "__API_ORIGIN__";           // e.g. https://capture.slidein.app
  var SITE_KEY = "__SITE_KEY__";
  var COOKIE = "__sl_vid";                     // first-party session cookie
  var MARKER = "he";                           // ?he=<token> query marker
  var COOKIE_TTL_DAYS = 365;

  /* ---------- first-party cookie helpers (no third-party storage) -------- */
  function setCookie(name, value, days) {
    var d = new Date();
    d.setTime(d.getTime() + days * 864e5);
    document.cookie = name + "=" + encodeURIComponent(value) +
      ";expires=" + d.toUTCString() + ";path=/;SameSite=Lax";
  }
  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : null;
  }

  /* ---------- ?he= interception + immediate session stitching ------------ */
  function interceptMarker() {
    var url = new URL(window.location.href);
    var token = url.searchParams.get(MARKER);
    if (!token) return getCookie(COOKIE);
    setCookie(COOKIE, token, COOKIE_TTL_DAYS);          // stitch on-device, first-party
    url.searchParams.delete(MARKER);                    // clean the URL bar
    window.history.replaceState(null, "", url.toString());
    return token;
  }

  /* ---------- Snowplow-style fingerprint vectors ------------------------- */
  function canvasVector() {
    try {
      var c = document.createElement("canvas");
      c.width = 240; c.height = 60;
      var ctx = c.getContext("2d");
      ctx.textBaseline = "top";
      ctx.font = "14px 'Arial'";
      ctx.fillStyle = "#f60";
      ctx.fillRect(0, 0, 100, 20);
      ctx.fillStyle = "#069";
      ctx.fillText("Slidein fp ~!@#$%^&*()_+{}[]", 2, 15);
      ctx.strokeStyle = "rgba(102, 204, 0, 0.7)";
      ctx.arc(50, 30, 18, 0, Math.PI * 2);
      ctx.stroke();
      return c.toDataURL();
    } catch (e) { return null; }
  }

  function collectFingerprint() {
    var nav = window.navigator || {};
    return {
      canvas: canvasVector(),
      user_agent: nav.userAgent,
      language: nav.language,
      languages: nav.languages || [],
      platform: nav.platform,
      hardware_concurrency: nav.hardwareConcurrency,
      device_memory: nav.deviceMemory || null,
      max_touch_points: nav.maxTouchPoints,
      timezone: (Intl.DateTimeFormat().resolvedOptions().timeZone || null),
      screen: { w: screen.width, h: screen.height, dpr: window.devicePixelRatio },
      color_depth: screen.colorDepth,
      plugins: (nav.plugins ? Array.prototype.map.call(nav.plugins, function (p) { return p.name; }) : []),
      do_not_track: nav.doNotTrack || null,
    };
  }

  /* ---------- async ingestion (RudderStack-style track payload) ---------- */
  function buildPayload(sessionId) {
    return {
      type: "track",
      event: "page_view",
      anonymous_id: fingerprintHash(collectFingerprint()),
      site_key: SITE_KEY,
      session_id: sessionId,
      query_marker_token: null,
      context: {
        ip: null,                       // server fills from socket
        user_agent: navigator.userAgent,
        page: {
          url: window.location.href,
          title: document.title,
          referrer: document.referrer || null,
        },
        fingerprint: collectFingerprint(),
        screen: { w: screen.width, h: screen.height },
      },
      sent_at: new Date().toISOString(),
    };
  }

  function fingerprintHash(fp) {
    var s = JSON.stringify(fp);
    var h = 0;
    for (var i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
    return "anon_" + (h >>> 0).toString(36);
  }

  function send(payload) {
    var body = JSON.stringify(payload);
    var url = API_ORIGIN + "/api/v1/capture/track";
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        if (navigator.sendBeacon(url, blob)) return;
      }
    } catch (e) { /* fall through to fetch */ }
    try {
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true,
        credentials: "omit",
      }).catch(function () {});
    } catch (e) { /* never break the client page */ }
  }

  /* ---------- boot -------------------------------------------------------- */
  function track() {
    var sessionId = interceptMarker();     // immediate ?he= stitching
    send(buildPayload(sessionId));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", track);
  } else {
    track();
  }
  window.addEventListener("pagehide", function () {
    var sessionId = getCookie(COOKIE);
    if (sessionId) send(buildPayload(sessionId));
  });
})();

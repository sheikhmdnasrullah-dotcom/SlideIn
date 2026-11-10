import { newTracker, trackPageView } from "@snowplow/browser-tracker";
import { RudderAnalytics } from "@rudderstack/analytics-js/bundled";

/**
 * Optional official analytics adapter for client-owned sites.
 *
 * Nothing initializes or sends automatically. A site must explicitly initialize
 * after its consent flow, with only the providers it has configured. This module
 * deliberately has no canvas/browser fingerprinting and no identity provider.
 */
let state = { initialized: false, providers: [], consent: false };
let rudder = null;

export function init(config = {}) {
  if (config.consent !== true) {
    throw new Error("Analytics consent is required before initialization");
  }
  if (state.initialized) return getStatus();

  const providers = [];
  if (config.snowplow) {
    const { collectorUrl, appId, siteKey } = config.snowplow;
    if (!collectorUrl || !appId || !siteKey) {
      throw new Error("Snowplow requires collectorUrl, appId, and siteKey");
    }
    newTracker(`slidein-${siteKey}`, collectorUrl, {
      appId,
      platform: "web",
      stateStorageStrategy: "cookieAndLocalStorage",
      cookieSameSite: "Lax",
    });
    providers.push("snowplow");
  }

  if (config.rudderstack) {
    const { writeKey, dataPlaneUrl, configUrl } = config.rudderstack;
    if (!writeKey || !dataPlaneUrl) {
      throw new Error("RudderStack requires writeKey and dataPlaneUrl");
    }
    rudder = new RudderAnalytics();
    rudder.load(writeKey, dataPlaneUrl, {
      configUrl,
      integrations: { All: false },
    });
    providers.push("rudderstack");
  }

  if (!providers.length) throw new Error("No analytics provider configured");
  state = { initialized: true, providers, consent: true };
  return getStatus();
}

export function trackPage(properties = {}) {
  if (!state.initialized) return false;
  if (state.providers.includes("snowplow")) trackPageView();
  if (rudder) rudder.page(properties);
  return true;
}

export function track(event, properties = {}) {
  if (!state.initialized || typeof event !== "string" || !event.trim()) return false;
  // RudderStack owns arbitrary custom events. Snowplow custom events require a
  // versioned Iglu schema, so do not emit an unstructured substitute here.
  if (rudder) rudder.track(event, properties);
  return Boolean(rudder);
}

export function identify(userId, traits = {}) {
  if (!state.initialized || !rudder || !userId) return false;
  // Identification is explicit and consented; never infer a person from IP.
  rudder.identify(String(userId), traits);
  return true;
}

export function getStatus() {
  return { ...state, providers: [...state.providers] };
}

export function resetForTest() {
  state = { initialized: false, providers: [], consent: false };
  rudder = null;
}

if (typeof window !== "undefined") {
  window.SlideinOfficialAnalytics = { init, trackPage, track, identify, getStatus };
}

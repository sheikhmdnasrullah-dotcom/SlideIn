package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// doProxyRequest runs a request through the proxy-header middleware and
// returns the RemoteAddr observed by the innermost handler.
func doProxyRequest(t *testing.T, handler func(http.Handler) http.Handler, remoteAddr string, headers map[string]string) string {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "http://example.com/", nil)
	req.RemoteAddr = remoteAddr
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	observed := ""
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		observed = r.RemoteAddr
	})
	handler(inner).ServeHTTP(httptest.NewRecorder(), req)
	return observed
}

// A directly exposed client must not be able to spoof its IP via
// X-Forwarded-For (this bypassed the login rate limiter before).
func TestProxyHeadersIgnoresForwardedHeadersFromUntrustedPeer(t *testing.T) {
	handler := ProxyHeaders(nil)
	got := doProxyRequest(t, handler, "203.0.113.50:12345", map[string]string{
		"X-Forwarded-For": "1.2.3.4",
		"X-Real-IP":       "1.2.3.4",
	})
	if got != "203.0.113.50:12345" {
		t.Fatalf("expected RemoteAddr to be left alone, got %q", got)
	}
}

// A trusted proxy (loopback by default) may supply the client address.
func TestProxyHeadersHonoursTrustedProxy(t *testing.T) {
	handler := ProxyHeaders(nil)
	got := doProxyRequest(t, handler, "127.0.0.1:9999", map[string]string{
		"X-Forwarded-For": "198.51.100.7",
	})
	if got != "198.51.100.7" {
		t.Fatalf("expected client IP from trusted proxy, got %q", got)
	}
}

// The rightmost X-Forwarded-For entry added by our proxy wins, even if the
// original client supplied a forged left-hand entry.
func TestProxyHeadersUsesNearestUntrustedHop(t *testing.T) {
	handler := ProxyHeaders(nil)
	got := doProxyRequest(t, handler, "10.0.0.2:4444", map[string]string{
		"X-Forwarded-For": "6.6.6.6, 198.51.100.7",
	})
	if got != "198.51.100.7" {
		t.Fatalf("expected nearest untrusted hop, got %q", got)
	}
}

// Explicitly configured proxies (e.g. a public load balancer) are trusted.
func TestProxyHeadersHonoursExplicitlyTrustedProxy(t *testing.T) {
	handler := ProxyHeaders([]string{"192.0.2.10/32"})
	got := doProxyRequest(t, handler, "192.0.2.10:5555", map[string]string{
		"X-Forwarded-For": "198.51.100.9",
	})
	if got != "198.51.100.9" {
		t.Fatalf("expected explicitly trusted proxy to be honoured, got %q", got)
	}

	// An untrusted peer remains unaffected even with the extra list set.
	handler = ProxyHeaders([]string{"192.0.2.10/32"})
	got = doProxyRequest(t, handler, "203.0.113.50:5555", map[string]string{
		"X-Forwarded-For": "198.51.100.9",
	})
	if got != "203.0.113.50:5555" {
		t.Fatalf("expected untrusted peer to be ignored, got %q", got)
	}
}

// An all-trusted chain yields no rewrite (no untrusted hop to identify).
func TestProxyHeadersAllTrustedChainKeepsPeer(t *testing.T) {
	handler := ProxyHeaders(nil)
	got := doProxyRequest(t, handler, "127.0.0.1:1", map[string]string{
		"X-Forwarded-For": "10.0.0.5",
	})
	if got != "127.0.0.1:1" {
		t.Fatalf("expected peer address to be kept, got %q", got)
	}
}

package middleware

import (
	"net"
	"net/http"
	"strings"
)

// defaultTrustedProxyNets lists the networks whose direct peers are assumed to
// be reverse proxies operated by us (loopback and RFC1918/ULA private space).
// Forwarding headers are only honoured when the immediate peer is in this set
// or in the explicitly configured trusted proxy list.
//
// This is the secure default: when the server is directly exposed to the
// internet, clients cannot spoof X-Forwarded-For to bypass IP-based rate
// limits or forge recorded visitor IPs.
var defaultTrustedProxyNets = parseProxyNets([]string{
	"127.0.0.0/8",
	"::1/128",
	"10.0.0.0/8",
	"172.16.0.0/12",
	"192.168.0.0/16",
	"fc00::/7",
	"fe80::/10",
})

// parseProxyNets converts CIDR blocks and bare IP addresses into networks.
// Invalid entries are skipped; callers configure this once at startup.
func parseProxyNets(entries []string) []*net.IPNet {
	nets := make([]*net.IPNet, 0, len(entries))
	for _, entry := range entries {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}
		if !strings.Contains(entry, "/") {
			ip := net.ParseIP(entry)
			if ip == nil {
				continue
			}
			bits := 32
			if ip.To4() == nil {
				bits = 128
			}
			nets = append(nets, &net.IPNet{IP: ip, Mask: net.CIDRMask(bits, bits)})
			continue
		}
		_, network, err := net.ParseCIDR(entry)
		if err != nil {
			continue
		}
		nets = append(nets, network)
	}
	return nets
}

func ipInNets(ip net.IP, nets []*net.IPNet) bool {
	for _, network := range nets {
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

func peerIP(remoteAddr string) net.IP {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		host = remoteAddr
	}
	return net.ParseIP(strings.TrimSpace(host))
}

// forwardedClientIP returns the client IP asserted by a trusted proxy chain.
// It walks X-Forwarded-For right-to-left and returns the first address that is
// not itself a trusted proxy (the nearest untrusted hop is the real client).
// It returns nil when no such address exists.
func forwardedClientIP(r *http.Request, trusted []*net.IPNet) net.IP {
	xff := r.Header.Get("X-Forwarded-For")
	if xff != "" {
		parts := strings.Split(xff, ",")
		for i := len(parts) - 1; i >= 0; i-- {
			ip := net.ParseIP(strings.TrimSpace(parts[i]))
			if ip == nil {
				// Unparseable entry: stop rather than trust further left.
				return nil
			}
			if !ipInNets(ip, trusted) {
				return ip
			}
		}
		return nil
	}
	if xri := strings.TrimSpace(r.Header.Get("X-Real-IP")); xri != "" {
		ip := net.ParseIP(xri)
		if ip != nil && !ipInNets(ip, trusted) {
			return ip
		}
	}
	return nil
}

// ProxyHeaders honours X-Forwarded-For / X-Real-IP / X-Forwarded-Proto only
// when the direct peer is a trusted reverse proxy. It replaces
// handlers.ProxyHeaders, which unconditionally let any client rewrite its own
// RemoteAddr and thereby bypass IP-keyed rate limits.
//
// trustedExtra lists additional proxies (CIDR or bare IP), e.g. a public load
// balancer IP. Default private/loopback ranges are always trusted.
func ProxyHeaders(trustedExtra []string) func(http.Handler) http.Handler {
	trusted := append(parseProxyNets(trustedExtra), defaultTrustedProxyNets...)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			peer := peerIP(r.RemoteAddr)
			if peer == nil || !ipInNets(peer, trusted) {
				// Direct/untrusted client: forwarding headers are attacker
				// controlled, so ignore them entirely.
				next.ServeHTTP(w, r)
				return
			}
			if client := forwardedClientIP(r, trusted); client != nil {
				r.RemoteAddr = client.String()
			}
			switch proto := strings.ToLower(r.Header.Get("X-Forwarded-Proto")); proto {
			case "http", "https":
				r.URL.Scheme = proto
			}
			if host := r.Header.Get("X-Forwarded-Host"); host != "" {
				r.Host = host
			}
			next.ServeHTTP(w, r)
		})
	}
}

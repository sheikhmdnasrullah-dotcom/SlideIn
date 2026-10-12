package config

import (
	"encoding/json"
	"io/ioutil"

	log "github.com/gophish/gophish/logger"
)

// AdminServer represents the Admin server configuration details
type AdminServer struct {
	ListenURL            string   `json:"listen_url"`
	UseTLS               bool     `json:"use_tls"`
	CertPath             string   `json:"cert_path"`
	KeyPath              string   `json:"key_path"`
	CSRFKey              string   `json:"csrf_key"`
	AllowedInternalHosts []string `json:"allowed_internal_hosts"`
	TrustedOrigins       []string `json:"trusted_origins"`
	// TrustedProxies lists reverse proxies (CIDR or bare IP) whose
	// X-Forwarded-For headers are honoured. Loopback and private ranges are
	// always trusted; add public load balancer addresses here when deployed
	// behind one. Forwarding headers from any other peer are ignored so
	// clients cannot spoof their IP past rate limits.
	TrustedProxies []string `json:"trusted_proxies"`
}

// PhishServer represents the Phish server configuration details
type PhishServer struct {
	ListenURL string `json:"listen_url"`
	UseTLS    bool   `json:"use_tls"`
	CertPath  string `json:"cert_path"`
	KeyPath   string `json:"key_path"`
	// TrustedProxies has the same meaning as AdminServer.TrustedProxies and
	// controls which peers may supply X-Forwarded-For for recorded visitor
	// IPs.
	TrustedProxies []string `json:"trusted_proxies"`
}

// LLMConfig represents the LLM configuration
type LLMConfig struct {
	APIKey      string  `json:"llm_api_key"`
	Model       string  `json:"llm_model"`
	Temperature float64 `json:"llm_temperature"`
	MaxTokens   int     `json:"llm_max_tokens"`
	Enabled     bool    `json:"llm_enabled"`
}

// Config represents the configuration information.
type Config struct {
	AdminConf       AdminServer `json:"admin_server"`
	PhishConf       PhishServer `json:"phish_server"`
	DBName          string      `json:"db_name"`
	DBPath          string      `json:"db_path"`
	DBSSLCaPath     string      `json:"db_sslca_path"`
	MigrationsPath  string      `json:"migrations_prefix"`
	TestFlag        bool        `json:"test_flag"`
	ContactAddress  string      `json:"contact_address"`
	XMailer         string      `json:"x_mailer"`
	MessageIDDomain string      `json:"message_id_domain"`
	// SendDelay is the number of seconds to sleep between sending each
	// individual email within a campaign. Defaults to 5 if unset.
	SendDelay    int         `json:"send_delay"`
	SendDelayMin int         `json:"send_delay_min"`
	SendDelayMax int         `json:"send_delay_max"`
	Logging      *log.Config `json:"logging"`
	LLMConf      *LLMConfig  `json:"llm"`
}

// Version contains the current gophish version
var Version = ""

// Conf holds the active runtime configuration, set in gophish.go after
// LoadConfig. Used by packages (e.g. mailer) that need config values without
// circular imports.
var Conf *Config

// ServerName is the default value used for the X-Mailer header and transparency
// response when no x_mailer is set in config.json.
const ServerName = "MS-Exchange"

// DefaultMessageIDDomain is the default domain used when generating Message-Id
// headers when no message_id_domain is set in config.json.
const DefaultMessageIDDomain = "mail.google.com"

// LoadConfig loads the configuration from the specified filepath
func LoadConfig(filepath string) (*Config, error) {
	// Get the config file
	configFile, err := ioutil.ReadFile(filepath)
	if err != nil {
		return nil, err
	}
	config := &Config{}
	err = json.Unmarshal(configFile, config)
	if err != nil {
		return nil, err
	}
	if config.Logging == nil {
		config.Logging = &log.Config{}
	}
	// Apply defaults for optional fields so old config.json files keep working.
	if config.MessageIDDomain == "" {
		config.MessageIDDomain = DefaultMessageIDDomain
	}
	// Default send delay to 5 seconds if not set or set to 0
	if config.SendDelay <= 0 {
		config.SendDelay = 5
	}
	// Initialize LLM config if not provided
	if config.LLMConf == nil {
		config.LLMConf = &LLMConfig{
			Model:       "openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition", // Hardcoded as requested
			Temperature: 0.7,
			MaxTokens:   4096,
			Enabled:     true,
		}
	}
	// Choosing the migrations directory based on the database used.
	config.MigrationsPath = config.MigrationsPath + config.DBName
	// Explicitly set the TestFlag to false to prevent config.json overrides
	config.TestFlag = false
	return config, nil
}

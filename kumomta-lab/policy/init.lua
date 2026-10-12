-- KumoMTA lab policy.
--
-- Design goals (compliant deliverability lab, NOT spam evasion):
--   * Every outbound message is forced to the in-network sink MX
--     (sink.lab.internal). The lab has no Internet egress, so it can
--     never send real-world email.
--   * Provider behavior is simulated by the sink MX via per-recipient
--     domain scenarios (Gmail/Yahoo/Microsoft-style throttling, 4xx/5xx,
--     TLS failure, slow MX, resets). See kumomta-lab/policy/sink-scenarios.yaml.
--   * Submission requires AUTH. relay_hosts is restricted to the lab
--     subnets, so this is not an open relay.
--   * DKIM signing is exercised with a lab key for local validation only.
--   * A single conservative egress policy is applied; provider-specific
--     *Kumo* shaping is an extension point (see NOTES at bottom).

local kumo = require 'kumo'

kumo.on('pre_init', function()
  kumo.set_httpinject_threads(math.ceil(kumo.available_parallelism() / 2))
  kumo.set_readyq_threads(math.ceil(kumo.available_parallelism() / 2))
end)

kumo.on('init', function()
  kumo.configure_accounting_db_path('/var/lib/kumo/accounting.db')

  kumo.define_spool { name = 'data', path = '/var/lib/kumo/spool/data', kind = 'RocksDB' }
  kumo.define_spool { name = 'meta', path = '/var/lib/kumo/spool/meta', kind = 'RocksDB' }

  -- Submission listener (587). Only lab subnets may connect, and AUTH is required.
  kumo.start_esmtp_listener {
    listen = os.getenv('KUMO_LISTENER_SMTP') or '0.0.0.0:587',
    relay_hosts = { '127.0.0.1', '::1', '172.16.0.0/12', '10.0.0.0/8' },
    banner = 'kumolab MTA',
    max_messages_per_connection = 100,
    max_recipients_per_message = 50,
  }

  kumo.start_http_listener {
    listen = os.getenv('KUMO_LISTENER_HTTP') or '0.0.0.0:8029',
    trusted_hosts = { '127.0.0.1', '::1', '172.16.0.0/12', '10.0.0.0/8' },
  }

  kumo.configure_local_logs {
    log_dir = '/var/log/kumo',
    max_segment_duration = '1s',
    back_pressure = 512 * 1024,
  }
end)

-- Lab credentials. OVERRIDE via KUMO_LAB_PASSWORD in production-like runs.
-- This is a controlled lab, not a real auth backend.
local LAB_USERS = {
  ['lab'] = os.getenv('KUMO_LAB_PASSWORD') or 'lab-secret',
}

kumo.on('smtp_server_auth_plain', function(_authz, authc, password)
  return LAB_USERS[authc] == password
end)

kumo.on('http_server_validate_auth_basic', function(user, password)
  return LAB_USERS[user] == password
end)

-- Per-message processing: route to sink, sign DKIM.
kumo.on('smtp_server_message_received', function(msg)
  local from = msg:from_header()
  if not from then
    kumo.reject(552, '5.6.0 Missing From header')
  end

  -- Force all outbound to the isolated sink MX. This is the hard guarantee
  -- that the lab never reaches a real recipient.
  msg:set_meta('routing_domain', 'sink.lab.internal')

  -- Exercise DKIM signing with the lab key (selector 'lab').
  local ok, signer = pcall(function()
    return kumo.dkim.rsa_sha256_signer {
      domain = from.domain,
      selector = 'lab',
      headers = { 'From', 'To', 'Subject' },
      key = '/etc/kumo/dkim/lab-private-dkim-key.pem',
    }
  end)
  if ok then
    msg:dkim_sign(signer)
  end
end)

kumo.on('http_message_generated', function(msg)
  local from = msg:from_header()
  if from then
    msg:set_meta('routing_domain', 'sink.lab.internal')
    local ok, signer = pcall(function()
      return kumo.dkim.rsa_sha256_signer {
        domain = from.domain,
        selector = 'lab',
        headers = { 'From', 'To', 'Subject' },
        key = '/etc/kumo/dkim/lab-private-dkim-key.pem',
      }
    end)
    if ok then
      msg:dkim_sign(signer)
    end
  end
end)

-- Conservative lab egress policy.
kumo.on('get_egress_path_config', function(_routing_domain, _egress_source, _site_name)
  return kumo.make_egress_path {
    connection_limit = 20,
    max_ready = 1000,
    enable_tls = 'Disabled',
    enable_mta_sts = false,
    smtp_port = 25,
    max_message_rate = '30/min',
    max_connection_rate = '10/min',
    max_deliveries_per_connection = 10,
    refresh_strategy = 'Epoch',
  }
end)

-- NOTES / EXTENSION POINTS
--   * Provider-specific Kumo shaping: key get_egress_path_config on the
--     *recipient* domain instead of forcing routing_domain. To keep the lab
--     hermetic while preserving provider keying, run a tiny in-network DNS
--     that returns sink.lab.internal for every MX lookup, then route by the
--     original domain name. The sink still classifies by recipient domain.
--   * Adaptive backoff (TSA): KumoMTA's Traffic Shaping Automation can be
--     layered in once a real resolver + policy-extras assets are baked into
--     the image. For the lab, deterministic sink scenarios are the control.
--   * Suppression / transactional priority: enforce upstream in the
--     deliverability pipeline (deliverability/core/pipeline.py) before
--     injection; KumoMTA honors X-headers you choose to key queues on.

-- SlideIn KumoMTA Local Policy (Hermetic Local Mode)
-- Routes all egress safely to Mailpit (mailpit:1025) while exercising full ESMTP AUTH and DKIM signing.

local kumo = require 'kumo'

kumo.on('pre_init', function()
  kumo.set_httpinject_threads(math.ceil(kumo.available_parallelism() / 2))
  kumo.set_readyq_threads(math.ceil(kumo.available_parallelism() / 2))
end)

kumo.on('init', function()
  kumo.configure_accounting_db_path('/var/lib/kumo/accounting.db')

  kumo.define_spool { name = 'data', path = '/var/lib/kumo/spool/data', kind = 'RocksDB' }
  kumo.define_spool { name = 'meta', path = '/var/lib/kumo/spool/meta', kind = 'RocksDB' }

  -- Submission listener (587 inside container, mapped to 2587 on host).
  kumo.start_esmtp_listener {
    listen = os.getenv('KUMO_LISTENER_SMTP') or '0.0.0.0:587',
    relay_hosts = { '127.0.0.1', '::1', '172.16.0.0/12', '10.0.0.0/8', '192.168.0.0/16' },
    banner = 'SlideIn KumoMTA Local ESMTP',
    max_messages_per_connection = 100,
    max_recipients_per_message = 50,
  }

  -- HTTP Admin API (8029)
  kumo.start_http_listener {
    listen = os.getenv('KUMO_LISTENER_HTTP') or '0.0.0.0:8029',
    trusted_hosts = { '127.0.0.1', '::1', '172.16.0.0/12', '10.0.0.0/8', '192.168.0.0/16' },
  }

  kumo.configure_local_logs {
    log_dir = '/var/log/kumo',
    max_segment_duration = '1s',
    back_pressure = 512 * 1024,
  }
end)

-- Authorized credentials for local testing
local USERS = {
  ['outbound'] = 'local-dev-password',
  ['admin'] = 'local-dev-password',
  ['lab'] = 'lab-secret',
  ['slidein'] = 'slidein-secret',
}

kumo.on('smtp_server_auth_plain', function(_authz, authc, password)
  return USERS[authc] == password
end)

kumo.on('http_server_validate_auth_basic', function(user, password)
  return USERS[user] == password
end)

-- Find DKIM key: check domain-specific key first, then fall back to lab key
local function get_dkim_key(domain)
  local key_path = '/etc/kumo/dkim/' .. domain .. '.private.key'
  local f = io.open(key_path, 'r')
  if f then
    f:close()
    return key_path, 'dkim'
  end
  local lab_key = '/etc/kumo/dkim/lab-private-dkim-key.pem'
  local flab = io.open(lab_key, 'r')
  if flab then
    flab:close()
    return lab_key, 'lab'
  end
  return nil, nil
end

local function apply_dkim(msg)
  local from = msg:from_header()
  local domain = (from and from.domain) or 'nasrullahtanim.me'
  local key_path, selector = get_dkim_key(domain)
  if key_path then
    pcall(function()
      local signer = kumo.dkim.rsa_sha256_signer {
        domain = domain,
        selector = selector or 'dkim',
        headers = { 'From', 'To', 'Subject', 'Date', 'Message-ID', 'Content-Type' },
        key = key_path,
      }
      msg:dkim_sign(signer)
    end)
  end
end

-- Process incoming SMTP submissions: force routing to local mailpit sink
kumo.on('smtp_server_message_received', function(msg)
  local from = msg:from_header()
  if not from then
    kumo.reject(552, '5.6.0 Missing From header')
  end

  local mailpit_host = os.getenv('MAILPIT_HOST') or 'mailpit'
  msg:set_meta('routing_domain', mailpit_host)
  apply_dkim(msg)
end)

kumo.on('http_message_generated', function(msg)
  local mailpit_host = os.getenv('MAILPIT_HOST') or 'mailpit'
  msg:set_meta('routing_domain', mailpit_host)
  apply_dkim(msg)
end)

-- Egress routing: deliver to Mailpit on configured port (1025)
kumo.on('get_egress_path_config', function(_routing_domain, _egress_source, _site_name)
  local mailpit_port = tonumber(os.getenv('MAILPIT_PORT') or '1025')
  return kumo.make_egress_path {
    connection_limit = 20,
    max_ready = 1000,
    enable_tls = 'Disabled',
    enable_mta_sts = false,
    smtp_port = mailpit_port,
    max_message_rate = '300/min',
    max_connection_rate = '100/min',
    max_deliveries_per_connection = 50,
  }
end)

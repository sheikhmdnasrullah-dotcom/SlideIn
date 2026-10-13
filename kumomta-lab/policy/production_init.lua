local kumo = require 'kumo'

kumo.on('pre_init', function()
  kumo.set_httpinject_threads(math.ceil(kumo.available_parallelism() / 2))
  kumo.set_readyq_threads(math.ceil(kumo.available_parallelism() / 2))
end)

kumo.on('init', function()
  kumo.configure_accounting_db_path('/var/lib/kumo/accounting.db')

  kumo.define_spool { name = 'data', path = '/var/lib/kumo/spool/data', kind = 'RocksDB' }
  kumo.define_spool { name = 'meta', path = '/var/lib/kumo/spool/meta', kind = 'RocksDB' }

  kumo.start_esmtp_listener {
    listen = '0.0.0.0:2587',
    -- Loopback + private docker networks (warmbly worker relays from
    -- 172.20.0.0/24 via STARTTLS+AUTH). Port 2587 is loopback-published
    -- and UFW-blocked, so no internet host can reach this listener.
    relay_hosts = { '127.0.0.1', '::1', '172.16.0.0/12', '10.0.0.0/8' },
    banner = 'mail.nasrullahtanim.me ESMTP',
    max_messages_per_connection = 100,
    max_recipients_per_message = 50,
    -- NOTE (2026-10-12): kumod 2026.09.x rejects `require_auth` (unknown
    -- field), so it was removed. Relay is governed by `relay_hosts`
    -- (loopback only) + loopback-only port publish + UFW. SMTP AUTH
    -- (smtp_server_auth_plain) is still offered and honored.
  }

  kumo.start_http_listener {
    listen = '0.0.0.0:8029',
    trusted_hosts = { '127.0.0.1', '::1', '172.16.0.0/12', '10.0.0.0/8' },
  }

  kumo.configure_local_logs {
    log_dir = '/var/log/kumo',
    max_segment_duration = '1s',
    back_pressure = 512 * 1024,
  }
end)

local secrets = dofile '/opt/kumomta/etc/policy/secrets.lua'

kumo.on('smtp_server_auth_plain', function(_authz, authc, password)
  return secrets.users[authc] == password
end)

kumo.on('http_server_validate_auth_basic', function(user, password)
  return secrets.users[user] == password
end)

local DOMAINS = {
  'nasrullahtanim.me',
  'tanim.social',
  'tanim.tech',
}

local function get_dkim_key(domain)
  local key_path = '/etc/kumo/dkim/' .. domain .. '.private.key'
  local f = io.open(key_path, 'r')
  if not f then
    return nil, 'key not found: ' .. key_path
  end
  f:close()
  return key_path
end

local function dkim_sign(msg, domain)
  local key_path, err = get_dkim_key(domain)
  if not key_path then
    kumo.log('DKIM key missing for ' .. domain .. ': ' .. err)
    return false
  end

  local ok, signer = pcall(function()
    return kumo.dkim.rsa_sha256_signer {
      domain = domain,
      selector = 'dkim',
      headers = { 'From', 'To', 'Subject', 'Date', 'Message-ID', 'MIME-Version', 'Content-Type' },
      key = key_path,
    }
  end)

  if ok then
    msg:dkim_sign(signer)
    return true
  else
    kumo.log('DKIM sign failed for ' .. domain .. ': ' .. tostring(signer))
    return false
  end
end

local function get_sending_domain(msg)
  local from = msg:from_header()
  if from and from.domain then
    return from.domain
  end
  return 'nasrullahtanim.me'
end

local function get_routing_domain(recipient)
  local domain = recipient:match('@(.+)$')
  if domain then
    return domain:lower()
  end
  return 'nasrullahtanim.me'
end

local function get_egress_for_domain(domain)
  local lower = domain:lower()
  if lower == 'gmail.com' then
    return {
      connection_limit = 10,
      max_ready = 1000,
      max_message_rate = '20/min',
      max_connection_rate = '5/min',
      max_deliveries_per_connection = 8,
      enable_tls = 'Opportunistic',
      smtp_port = 25,
    }
  elseif lower == 'yahoo.com' or lower == 'yahoo.co.jp' then
    return {
      connection_limit = 8,
      max_ready = 800,
      max_message_rate = '15/min',
      max_connection_rate = '3/min',
      max_deliveries_per_connection = 5,
      enable_tls = 'Opportunistic',
      smtp_port = 25,
    }
  elseif lower:find('outlook') or lower:find('hotmail') or lower:find('live') then
    return {
      connection_limit = 8,
      max_ready = 800,
      max_message_rate = '15/min',
      max_connection_rate = '3/min',
      max_deliveries_per_connection = 5,
      enable_tls = 'Opportunistic',
      smtp_port = 25,
    }
  elseif lower == 'apple.com' or lower == 'icloud.com' then
    return {
      connection_limit = 5,
      max_ready = 500,
      max_message_rate = '10/min',
      max_connection_rate = '2/min',
      max_deliveries_per_connection = 4,
      enable_tls = 'Opportunistic',
      smtp_port = 25,
    }
  else
    return {
      connection_limit = 10,
      max_ready = 1000,
      max_message_rate = '25/min',
      max_connection_rate = '5/min',
      max_deliveries_per_connection = 8,
      enable_tls = 'Opportunistic',
      smtp_port = 25,
    }
  end
end

local function get_source_for_domain(domain)
  if domain == 'nasrullahtanim.me' then
    return 'mail.nasrullahtanim.me'
  elseif domain == 'tanim.social' then
    return 'email.tanim.tech'
  elseif domain == 'tanim.tech' then
    return 'email.tanim.tech'
  end
  return 'mail.nasrullahtanim.me'
end

kumo.on('smtp_server_message_received', function(msg)
  local from = msg:from_header()
  if not from then
    kumo.reject(552, '5.6.0 Missing From header')
    return
  end

  local from_domain = from.domain or 'nasrullahtanim.me'

  if not get_dkim_key(from_domain) then
    kumo.log('No DKIM key for ' .. from_domain .. ', using default')
    from_domain = 'nasrullahtanim.me'
  end

  dkim_sign(msg, from_domain)

  msg:set_meta('egress_source', get_source_for_domain(from_domain))
end)

kumo.on('http_message_generated', function(msg)
  local from = msg:from_header()
  if from then
    local from_domain = from.domain or 'nasrullahtanim.me'
    if not get_dkim_key(from_domain) then
      from_domain = 'nasrullahtanim.me'
    end
    dkim_sign(msg, from_domain)
    msg:set_meta('egress_source', get_source_for_domain(from_domain))
  end
end)

kumo.on('get_egress_path_config', function(routing_domain, egress_source, site_name)
  local domain = routing_domain or 'nasrullahtanim.me'
  local config = get_egress_for_domain(domain)

  return kumo.make_egress_path {
    -- EHLO identifies the sending server (not the sender domain): one
    -- hostname that resolves to this VPS. Never use email.tanim.tech
    -- (points at 153.76.249.166, not us).
    ehlo_domain = 'mail.nasrullahtanim.me',
    connection_limit = config.connection_limit,
    max_ready = config.max_ready,
    enable_tls = config.enable_tls,
    enable_mta_sts = false,
    smtp_port = config.smtp_port,
    max_message_rate = config.max_message_rate,
    max_connection_rate = config.max_connection_rate,
    max_deliveries_per_connection = config.max_deliveries_per_connection,
    refresh_strategy = 'Epoch',
    connection_max_idle_time = '30s',
  }
end)

kumo.on('get_connection_config', function(remote_host, _egress_source, _site_name)
  return kumo.make_connection_config {
    tls = { mode = 'opportunistic', min_version = '1.2' },
    max_messages = 100,
    max_idle_time = '30s',
  }
end)

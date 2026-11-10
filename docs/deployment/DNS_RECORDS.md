# DNS Records — SlideIn Production (VPS <PRIMARY_VPS_IP>)

Generated 2026-10-12 from the live deploy. Values are public by design
(they are published in DNS). Apply in Cloudflare, then set the PTR in the
Contabo panel.

## Mail authentication (UPDATE existing records — old keys are stale)

The current SPF/DKIM records point at the decommissioned VPS. Until these
are updated, outbound mail from the new VPS fails SPF and DKIM.

### nasrullahtanim.me

| Type | Name | Value |
|------|------|-------|
| TXT | `@` (SPF, replace existing) | `v=spf1 ip4:<PRIMARY_VPS_IP> mx -all` |
| TXT | `dkim._domainkey` (replace existing) | `v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArRkLso9DMwB+uNNlLZRBWfeUVsjd9gTxHrmOJqjReVytwjPnruWv6IXs6ag8UJXJJK7wx8DUsusy846BIzILJVk3TZ2ATe9uSX9dT2xexmJYJRTavtgvOlRc1b3N9D89mGnNre6TiBaUbhYooY7HfnnBODQefz+OpRGENdrAF6aztmpInex60sBTEYkZfQboqy7TJaW7jmFmEQzlUxio//eqbJc1gDRAdJ751q1RfnwIK5tT+E/+nwabWxcNbaXhTsmqpLFsYMG1YaFK569cXs3FT3IzXtC01VH2AtOcXxoqK76fG8RMIUspfsBvA6i9KMX0RhaJGKUGo5h/eDnbEQIDAQAB` |
| TXT | `_dmarc` (keep if present) | `v=DMARC1; p=quarantine; rua=mailto:dmarc@nasrullahtanim.me; adkim=s; aspf=s` |
| A | `mail` | `<PRIMARY_VPS_IP>` |

### tanim.social

| Type | Name | Value |
|------|------|-------|
| TXT | `@` (SPF, replace existing) | `v=spf1 ip4:<PRIMARY_VPS_IP> mx -all` |
| TXT | `dkim._domainkey` (replace existing) | `v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuM0GL4W2MnrbsVEtsBFbJM71fNbMrJ4cgDtptS/1S/H3GBCNiq6EA34i24RSh5899YIotISBm6rCecr/2zGfe5WbZQNLC8+r5MGU62SDo3vq5ktYCBTjPvNKxyhDxddjVu5A/0FbM6mxgHb/f2VBsKyckSEZZkI4KEAmm5vfb/rpvGL6nd/G6yPyNgvBJ0lAecBzU2XloWa4o5xl91vUBf7ygdlUAUy5fM3Pa7hkHf4HaWktNz/r3DvnfOP42ST/WiyU5r231scnOCtkSvtBa/IWJ4ohhmrXZjN0Y8MKEknHNeI/sD7fLSOjtRaYuOuBq5ZFSN948kgSHC3CZhqwDQIDAQAB` |
| TXT | `_dmarc` (keep if present) | `v=DMARC1; p=quarantine; rua=mailto:dmarc@tanim.social; adkim=s; aspf=s` |

### tanim.tech

| Type | Name | Value |
|------|------|-------|
| TXT | `@` (SPF, replace existing) | `v=spf1 ip4:<PRIMARY_VPS_IP> mx -all` |
| TXT | `dkim._domainkey` (replace existing) | `v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwviwzh2SPggdQ0bsXUimOXEPA6ocHn9QWtgKOr7/GDWtArhedAiLDaNEoD+PUmajE3oluFf773UBZxhMQmcZ0koLYKMwCjsDufM5Ixj0axftLHYTVi8w2xUFMpd8tm5Zh96BYV9F1r2m655dgHq9MxVTmjdRlzmWQj8Uod4VAVu/llPAofWO2R79Kdg0eSFxQNer+Hq6hJFxImPQIP8aD+XNzr7xs9BD2fVfaJA0eNuL8reoVv9KfVgz2BNmOkqQr1vylRiOt0IiWb9SLJQrYFKK4YbZGrEEeNcXq7ZWDtIEkKWAd8QcAc/vfp0oyuXMy14fXQJUOUXYomAv5iyJ5wIDAQAB` |
| TXT | `_dmarc` (keep if present) | `v=DMARC1; p=quarantine; rua=mailto:dmarc@tanim.tech; adkim=s; aspf=s` |

### Reverse DNS (Contabo panel, not Cloudflare)

Set PTR for `<PRIMARY_VPS_IP>` to `mail.nasrullahtanim.me`.

## Website (ADD — required for https://www.slideinventure.com)

| Type | Name | Value |
|------|------|-------|
| A | `@` | `<PRIMARY_VPS_IP>` |
| CNAME | `www` | `cname.vercel-dns.com` (marketing site — do not repoint) |
| A | `app` | `<PRIMARY_VPS_IP>` |
| A | `console` | `<PRIMARY_VPS_IP>` (GoPhish campaign console, DNS-only) |
| A | `track` | `<PRIMARY_VPS_IP>` |
| A | `warmbly` | `<PRIMARY_VPS_IP>` |
| A | `warmbly-api` | `<PRIMARY_VPS_IP>` |
| A | `warmbly-track` | `<PRIMARY_VPS_IP>` |
| A | `api` | `<PRIMARY_VPS_IP>` (slidein-api agent workflow backend) |
| A | `workspace` | `<PRIMARY_VPS_IP>` (slidein-app client workspace UI) |

Use DNS-only (grey cloud) until Caddy has issued certificates; proxied
(orange cloud) also works since Caddy follows HTTP-01 behind Cloudflare,
but DNS-only is the predictable path for first issuance.

## Verify after applying (wait ~5 min)

```bash
dig +short TXT nasrullahtanim.me
dig +short TXT dkim._domainkey.nasrullahtanim.me
dig +short A www.slideinventure.com
ssh -i ~/.ssh/slidein_vps root@<PRIMARY_VPS_IP> 'cd /opt/deliverability && python3 cli.py precheck'
curl -sI https://www.slideinventure.com | head -3
```

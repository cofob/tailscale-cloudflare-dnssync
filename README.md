# tailscale-cloudflare-dnssync
Syncs Tailscale (or Headscale) host IPs to a cloudflare hosted DNS zone.
Basically works like Magic DNS, but with your domain.
The main benefit for me is the ability to use letsencrypt with certbot + dns challenge

## Documentation

- [README.md](README.md) - This file with usage instructions
- [FORK_SUMMARY.md](FORK_SUMMARY.md) - Overview of this fork and its purpose
- [CHANGELOG.md](CHANGELOG.md) - Complete changelog since the fork

## Features
- Adds ipv4 and ipv6 records for all devices
- Creates IPv4-only and IPv6-only subdomains (configurable)
- Removes DNS records for deleted devices
- Updates DNS records after the hostname/alias changes
- Add a pre- and/or postfixes to dns records
- Uses Tailscale machine "name" (not OS hostname) for DNS labels
- Optional tag filtering to include only devices with specified Tailscale tags
- Checks if DNS records is part of tailscale network (100.64.0.0/12 or fd7a:115c:a1e0::/48) before deleting records :P
- Support Tailscale and Headscale (tested with v0.22.3)


## Run
### Run using docker (using env var)
```shell
docker run --rm -it --env-file ~/git/tailscale-cloudflare-dnssync/env.txt ghcr.io/cofob/tailscale-cloudflare-dnssync
```

Envfile:
```env
# mode=<tailscale or headscale, default to tailscale if empty, optional>
cf-key=<cloudflare api key>
cf-domain=<cloudflare target zone>
# cf-sub=<subdomain to use, optional>
# cf-sub-ipv4=<IPv4-only subdomain to use, optional>
# cf-sub-ipv6=<IPv6-only subdomain to use, optional>

ts-key=<tailscale api key>
ts-tailnet=<tailnet>
# ts-clientid=<oauth clientid, optional>
# ts-clientsecret=<oauth clientsecret, optional>
# ts-tag-filter=tag:web,tag:prod   # optional; comma-separated list; include only devices with any of these tags

# prefix=<prefix for dns records, optional>
# postfix=<postfix for dns records, optional>
```
> **ts-tailnet** can be found in the [Tailscale Settings](https://login.tailscale.com/admin/settings/general)
```Settings -> General -> Organization``` or at the top left on the admin panel.

### Run using docker (using secrets)
```yaml
secrets:
  cf-key:
    file: "./cloudflare-key.txt"
  # either, use ts-key for an api key or ts-clientid and ts-clientsecret for oauth
  ts-key:
    file: "./tailscale-key.txt"
  ts-clientid:
    file: "./tailscale-clientid.txt" 
  ts-clientsecret:
    file: "./tailscale-clientsecret.txt"

services:
  cloudflare-dns-sync:
    image: ghcr.io/ç/tailscale-cloudflare-dnssync
    environment:
      - ts_tailnet=<tailnet>
      - cf_domain=example.com
      - cf_sub=sub      # optional, uses sub domain for dns records
      - cf_sub_ipv4=ts4 # optional, uses IPv4-only subdomain for dns records
      - cf_sub_ipv6=ts6 # optional, uses IPv6-only subdomain for dns records
      - prefix=ts-      # optional, adds prefix to dns records
      - postfix=-ts     # optional, adds postfix to dns records
    secrets:
      - cf-key
      - ts-key
```

### Run native using python
#### setup environment
```
python3 -m venv env
source env/bin/activate
pip install -r app/requirements.txt
cd app
python app.py
```
#### config.ini
```ini
[DEFAULT]
mode=               # optional; tailscale or headscale; defaults to tailscale

cf-key=             # mandatory; cloudflare api key
cf-domain=          # mandatory; cloudflare domain
cf-sub=             # optional; add a subdomain
cf-sub-ipv4=        # optional; add an IPv4-only subdomain
cf-sub-ipv6=        # optional; add an IPv6-only subdomain

ts-tailnet=         # mandatory in tailscale mode; tailnet name
ts-key=             # mandatory in tailscale mode if apikey is used; tailscale api
ts-client-id=       # mandatory in tailscale mode if oauth is used; tailscale oauth client id
ts-client-secret=   # mandatory in tailscale mode if oauth is used; tailscale oauth client secret
ts-tag-filter=      # optional; comma-separated list of tags; devices must have at least one to be synced

hs-baseurl=         # mandatory in headscale mode; headscale url
hs-apikey=          # mandatory in headscale mode; headscale apikey
```

## Run with headscale
### Env Example
```env
mode=headscale
cf-key=<cloudflare api key>
cf-domain=<cloudflare target zone>

hs-baseurl=https://headscale.example.com
hs-apikey=≤headscale api key>
```

## How to get API Keys
### Cloudflare
1. Login to Cloudflare Dashboard
2. Create API Key at https://dash.cloudflare.com/profile/api-tokens
3. Template: Edit Zone
4. Permissions: 
```
Permission | Zone - DNS - edit
Resource | include - specific zone - <your zone>
```

### Tailscale
#### API Key
1. Login to Tailscale website
2. Create API key at: https://login.tailscale.com/admin/settings/authkeys

#### OAuth
1. Login to Tailscale website
2. Create OAuth client at: https://login.tailscale.com/admin/settings/oauth with Devices Read permission

### Headscale
#### API Key
1. Create a API Key using ```headscale apikeys create --expiration 90d```

Docs: [Controlling headscale with remote CLI](https://github.com/juanfont/headscale/blob/main/docs/remote-cli.md#create-an-api-key)

## Usage Examples

### Dual-stack with IPv4-only and IPv6-only subdomains
If you want to create multiple subdomains for different IP versions:

```env
cf-domain=cfb.wtf
cf-sub=ts          # Creates dual-stack records: hostname.ts.cfb.wtf (A + AAAA)
cf-sub-ipv4=ts4    # Creates IPv4-only records: hostname.ts4.cfb.wtf (A only)
cf-sub-ipv6=ts6    # Creates IPv6-only records: hostname.ts6.cfb.wtf (AAAA only)
```

This will create:
- `hostname.ts.cfb.wtf` - Dual-stack (both A and AAAA records)
- `hostname.ts4.cfb.wtf` - IPv4-only (A record only)
- `hostname.ts6.cfb.wtf` - IPv6-only (AAAA record only)

Each subdomain will only contain records for devices with the appropriate IP version.

### Filter by Tailscale tags
Limit syncing to devices that have at least one of the specified tags:

```env
ts-tag-filter=tag:web,tag:prod
```

Shorthand without the `tag:` prefix is also accepted:

```env
ts-tag-filter=web,prod
```

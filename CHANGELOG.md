# Changelog

This document tracks all changes made to this fork of `tailscale-cloudflare-dnssync` since the original fork point at commit `1dab250a0b01e508827dd55ec0345a95036848a0`.

## [v4, Unreleased] - 2025-08-10

### Added
- **Tag filtering**: Optional filtering to sync only devices that have at least one of the specified Tailscale tags
  - New config key: `ts-tag-filter` (comma-separated list). Accepts values with or without the `tag:` prefix, e.g. `web,prod` or `tag:web,tag:prod`.

### Changed
- **Hostname source**: Use Tailscale machine `name` (first label) instead of OS `hostname`
- **Hostname cleanup**: Normalize labels before syncing to Cloudflare (lowercase, replace spaces/underscores with `-`, remove invalid characters, collapse dashes, trim leading/trailing `-.`)

### Configuration
```env
# Optional: include only devices matching any of these tags
ts-tag-filter=tag:web,tag:prod
```

## [v3] - 2025-08-10

### Added
- **IPv4-only and IPv6-only subdomain support**: New configuration options to create separate subdomains for IPv4 and IPv6 records
  - `cf-sub-ipv4`: Creates A records only for IPv4 devices (e.g., `hostname.ts4.domain.com`)
  - `cf-sub-ipv6`: Creates AAAA records only for IPv6 devices (e.g., `hostname.ts6.domain.com`)
- **Enhanced DNS record management**: Smart filtering ensures IPv4 devices only get A records in IPv4 subdomains and IPv6 devices only get AAAA records in IPv6 subdomains
- **Example configuration file**: Added `example.env` with comprehensive configuration examples
- **Improved documentation**: Updated README with usage examples and configuration details
- **Comprehensive documentation**: Added CHANGELOG.md, FORK_SUMMARY.md, and detailed commit history

### Changed
- **Configuration structure**: Added new optional configuration keys for IPv4/IPv6 subdomains
- **DNS record creation logic**: Enhanced to handle multiple subdomain types simultaneously
- **Cleanup logic**: Updated to properly manage records across all configured subdomains

### Configuration
The new functionality can be enabled by adding these optional configuration values:
```env
cf-sub=ts          # Dual-stack subdomain (existing behavior)
cf-sub-ipv4=ts4    # IPv4-only subdomain
cf-sub-ipv6=ts6    # IPv6-only subdomain
```

## [v2] - 2025-01-03

### Added
- **DNS record comments**: Added `@managed by auto-sync script` comment to all created DNS records for better identification

### Changed
- **Docker optimization**: Changed base image from `python:3.8` to `python:3.8-slim` for smaller image size
- **CI/CD optimization**: Removed multi-platform builds, now builds only for x86 architecture
- **Code cleanup**: Removed trailing whitespace and improved code formatting

### Fixed
- **Token handling**: Added `.strip()` calls to all API tokens to handle potential whitespace issues
  - Applied to Cloudflare API tokens in all functions
  - Applied to Tailscale API keys, client IDs, and client secrets
- **CI trigger**: Minor code cleanup to trigger CI pipeline

## Summary of Changes Since Fork

### Files Modified
- `.github/workflows/docker-publish.yml` - CI/CD optimization
- `app/Dockerfile` - Docker image optimization
- `app/app.py` - Major feature additions and code cleanup
- `app/cloudflare.py` - Token handling improvements and DNS record comments
- `app/config.ini` - New configuration options
- `app/config.py` - Configuration handling updates
- `app/tailscale.py` - Token handling improvements
- `README.md` - Comprehensive documentation updates
- `example.env` - New example configuration file

### Key Improvements
1. **Multi-subdomain DNS management** - The most significant addition allowing flexible DNS record organization
2. **Better token handling** - Improved reliability by stripping whitespace from all API tokens
3. **Docker optimization** - Smaller, more efficient container images
4. **Enhanced documentation** - Comprehensive examples and usage instructions
5. **Code quality** - Better formatting and structure

### Backward Compatibility
All changes maintain backward compatibility. The new IPv4/IPv6 subdomain functionality is completely optional and can be enabled by simply adding the new configuration values. Existing deployments will continue to work without modification.

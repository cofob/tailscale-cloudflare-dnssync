# Fork Summary

## Overview

This repository is a fork of the original `tailscale-cloudflare-dnssync` project, forked at commit `1dab250a0b01e508827dd55ec0345a95036848a0`. The fork has been enhanced with new features, improvements, and optimizations.

## Fork Purpose

The original project provided basic Tailscale/Headscale to Cloudflare DNS synchronization. This fork extends that functionality with:

1. **Enhanced DNS Management**: IPv4-only and IPv6-only subdomain support
2. **Better Reliability**: Improved token handling and error management
3. **Optimized Infrastructure**: Smaller Docker images and faster CI/CD
4. **Comprehensive Documentation**: Detailed examples and usage instructions

## Key Differences from Original

### New Features
- **Multi-subdomain DNS support**: Create separate subdomains for different IP versions
- **Smart record filtering**: Automatically route records to appropriate subdomains
- **Enhanced configuration**: More flexible configuration options

### Improvements
- **Token handling**: Better whitespace management for API tokens
- **Docker optimization**: Slimmer base images for reduced size
- **CI/CD optimization**: Faster, more efficient build processes
- **Code quality**: Better formatting and structure

### Documentation
- **Comprehensive examples**: Real-world configuration examples
- **Feature documentation**: Detailed explanation of new capabilities
- **Change tracking**: Complete changelog and commit history

## Migration from Original

### Backward Compatibility
- All existing configurations continue to work unchanged
- New features are completely optional
- No breaking changes to existing functionality

### Enabling New Features
To use the new IPv4/IPv6 subdomain functionality, simply add these optional configuration values:

```env
# Existing configuration (unchanged)
cf-domain=yourdomain.com
cf-sub=ts

# New optional features
cf-sub-ipv4=ts4    # IPv4-only subdomain
cf-sub-ipv6=ts6    # IPv6-only subdomain
```

### Benefits
- **Better organization**: Separate subdomains for different IP versions
- **Improved management**: Easier to manage and monitor DNS records
- **Flexible deployment**: Choose which features to enable
- **Enhanced reliability**: Better error handling and token management

## License

This fork maintains the same license as the original project. Please refer to the original project's license terms.

## Acknowledgments

- Original project maintainers for the excellent base implementation
- Community contributors for feedback and testing
- Users for feature requests and bug reports

---

For detailed information about all changes, see:
- [CHANGELOG.md](CHANGELOG.md) - Complete changelog

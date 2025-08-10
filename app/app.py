import ipaddress

from cloudflare import (
    createDNSRecord,
    deleteDNSRecord,
    getZoneId,
    getZoneRecords,
    isValidDNSRecord,
)
from config import getConfig
from tailscale import cleanHostname, getTailscaleDevice, isTailscaleIP
from termcolor import colored, cprint


def main() -> None:
    config = getConfig()
    cf_ZoneId = getZoneId(config["cf-key"], config["cf-domain"])
    cf_recordes = getZoneRecords(config["cf-key"], config["cf-domain"], zoneId=cf_ZoneId)

    # Get records depeneding on mode
    if config["mode"] == "tailscale":
        ts_records = getTailscaleDevice(
            config["ts-key"],
            config["ts-client-id"],
            config["ts-client-secret"],
            config["ts-tailnet"],
        )
    if config["mode"] == "headscale":
        from headscale import getHeadscaleDevice

        ts_records = getHeadscaleDevice(config["hs-apikey"], config["hs-baseurl"])

    records_typemap = {4: "A", 6: "AAAA"}

    print(
        colored("runnning in ", "blue") + colored(config["mode"], "red"),
        colored("mode", "blue") + "\n",
    )

    cprint("Adding new devices:", "blue")

    # Check if current hosts already have records:
    for ts_rec in ts_records:
        hostname_clean = cleanHostname(ts_rec["hostname"]) if ts_rec.get("hostname") else ""
        if not hostname_clean:
            print(
                "[{state}]: {host} -> (empty after cleanup, skipping)".format(
                    host=ts_rec.get("hostname", ""), state=colored("SKIPPING", "red")
                )
            )
            continue
        # if ts_rec['hostname'] in cf_recordes['name']:
        cf_sub = config.get("cf-sub") or ""
        sub = "." + cf_sub.lower() if cf_sub else ""
        tsfqdn = hostname_clean + sub + "." + config["cf-domain"]
        ip = ipaddress.ip_address(ts_rec["address"])

        # Check if dual-stack record already exists
        if any(c["name"] == tsfqdn and c["content"] == ts_rec["address"] for c in cf_recordes):
            print(
                "[{state}]: {host} -> {ip}".format(
                    host=tsfqdn, ip=ts_rec["address"], state=colored("FOUND", "green")
                )
            )
        elif isValidDNSRecord(hostname_clean):
            print(
                "[{state}]: {host} -> {ip}".format(
                    host=tsfqdn,
                    ip=ts_rec["address"],
                    state=colored("ADDING", "yellow"),
                )
            )
            createDNSRecord(
                config["cf-key"],
                config["cf-domain"],
                hostname_clean,
                records_typemap[ip.version],
                ts_rec["address"],
                subdomain=config["cf-sub"],
                zoneId=cf_ZoneId,
            )
        else:
            print(
                '[{state}]: {host}.{tld} -> {ip} -> (Hostname: "{host}.{tld}" is not valid)'.format(
                    host=hostname_clean,
                    ip=ts_rec["address"],
                    state=colored("SKIPING", "red"),
                    tld=config["cf-domain"],
                )
            )

        # Create IPv4-only subdomain records if configured
        if config.get("cf-sub-ipv4") and ip.version == 4:
            ipv4_raw = config.get("cf-sub-ipv4") or ""
            ipv4_sub = "." + ipv4_raw.lower()
            ipv4_fqdn = hostname_clean + ipv4_sub + "." + config["cf-domain"]

            if any(
                c["name"] == ipv4_fqdn and c["content"] == ts_rec["address"] for c in cf_recordes
            ):
                print(
                    "[{state}]: {host} -> {ip}".format(
                        host=ipv4_fqdn,
                        ip=ts_rec["address"],
                        state=colored("FOUND", "green"),
                    )
                )
            else:
                print(
                    "[{state}]: {host} -> {ip}".format(
                        host=ipv4_fqdn,
                        ip=ts_rec["address"],
                        state=colored("ADDING", "yellow"),
                    )
                )
                createDNSRecord(
                    config["cf-key"],
                    config["cf-domain"],
                    hostname_clean,
                    "A",
                    ts_rec["address"],
                    subdomain=config["cf-sub-ipv4"],
                    zoneId=cf_ZoneId,
                )

        # Create IPv6-only subdomain records if configured
        if config.get("cf-sub-ipv6") and ip.version == 6:
            ipv6_raw = config.get("cf-sub-ipv6") or ""
            ipv6_sub = "." + ipv6_raw.lower()
            ipv6_fqdn = hostname_clean + ipv6_sub + "." + config["cf-domain"]

            if any(
                c["name"] == ipv6_fqdn and c["content"] == ts_rec["address"] for c in cf_recordes
            ):
                print(
                    "[{state}]: {host} -> {ip}".format(
                        host=ipv6_fqdn,
                        ip=ts_rec["address"],
                        state=colored("FOUND", "green"),
                    )
                )
            else:
                print(
                    "[{state}]: {host} -> {ip}".format(
                        host=ipv6_fqdn,
                        ip=ts_rec["address"],
                        state=colored("ADDING", "yellow"),
                    )
                )
                createDNSRecord(
                    config["cf-key"],
                    config["cf-domain"],
                    hostname_clean,
                    "AAAA",
                    ts_rec["address"],
                    subdomain=config["cf-sub-ipv6"],
                    zoneId=cf_ZoneId,
                )

    cprint("Cleaning up old records:", "blue")
    # Check for old records:
    cf_recordes = getZoneRecords(config["cf-key"], config["cf-domain"])

    # set tailscale hostnames to lower cause dns is
    for i in range(len(ts_records)):
        ts_records[i]["hostname"] = ts_records[i]["hostname"].lower()

    for cf_rec in cf_recordes:
        domain = config["cf-domain"]
        cf_sub = config.get("cf-sub") or ""
        main_sub = "." + cf_sub.lower() if cf_sub else ""
        ipv4_raw = config.get("cf-sub-ipv4") or ""
        ipv4_sub = "." + ipv4_raw.lower() if ipv4_raw else ""
        ipv6_raw = config.get("cf-sub-ipv6") or ""
        ipv6_sub = "." + ipv6_raw.lower() if ipv6_raw else ""

        cf_name = None
        if ipv4_sub and cf_rec["name"].endswith(ipv4_sub + "." + domain):
            cf_name = cf_rec["name"].rsplit(ipv4_sub + "." + domain, 1)[0]
        elif ipv6_sub and cf_rec["name"].endswith(ipv6_sub + "." + domain):
            cf_name = cf_rec["name"].rsplit(ipv6_sub + "." + domain, 1)[0]
        elif main_sub and cf_rec["name"].endswith(main_sub + "." + domain):
            cf_name = cf_rec["name"].rsplit(main_sub + "." + domain, 1)[0]
        elif not main_sub and cf_rec["name"].endswith("." + domain):
            cf_name = cf_rec["name"].rsplit("." + domain, 1)[0]
        else:
            # Skip records that don't match any of our managed subdomains
            continue

        # Ignore any records not matching our prefix/postfix
        if not cf_name.startswith(config.get("prefix", "")):
            continue
        if not cf_name.endswith(config.get("postfix", "")):
            continue

        if any(a["hostname"] == cf_name and a["address"] == cf_rec["content"] for a in ts_records):
            print(
                "[{state}]: {host} -> {ip}".format(
                    host=cf_rec["name"],
                    ip=cf_rec["content"],
                    state=colored("IN USE", "green"),
                )
            )
        else:
            if not isTailscaleIP(cf_rec["content"]):
                msg = (
                    "[{state}]: {host} -> {ip} (IP does not belong to a tailscale host. "
                    "please remove manualy)"
                ).format(
                    host=cf_rec["name"],
                    ip=cf_rec["content"],
                    state=colored("SKIP DELETE", "red"),
                )
                print(msg)
                continue

            print(
                "[{state}]: {host} -> {ip}".format(
                    host=cf_rec["name"],
                    ip=cf_rec["content"],
                    state=colored("DELETING", "yellow"),
                )
            )
            deleteDNSRecord(config["cf-key"], config["cf-domain"], cf_rec["id"], zoneId=cf_ZoneId)


if __name__ == "__main__":
    main()

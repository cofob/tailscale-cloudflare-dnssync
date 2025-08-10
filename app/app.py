import ipaddress
import json

from requests.api import delete
from termcolor import colored, cprint

from cloudflare import (
    createDNSRecord,
    deleteDNSRecord,
    getZoneRecords,
    isValidDNSRecord,
    getZoneId,
)
from tailscale import getTailscaleDevice, isTailscaleIP
from config import getConfig

import sys


def main():
    config = getConfig()
    cf_ZoneId = getZoneId(config["cf-key"], config["cf-domain"])
    cf_recordes = getZoneRecords(
        config["cf-key"], config["cf-domain"], zoneId=cf_ZoneId
    )

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
        # if ts_rec['hostname'] in cf_recordes['name']:
        if config.get("cf-sub"):
            sub = "." + config.get("cf-sub").lower()
        else:
            sub = ""
        tsfqdn = ts_rec["hostname"].lower() + sub + "." + config["cf-domain"]

        # Check if dual-stack record already exists
        if any(
            c["name"] == tsfqdn and c["content"] == ts_rec["address"]
            for c in cf_recordes
        ):
            print(
                "[{state}]: {host} -> {ip}".format(
                    host=tsfqdn, ip=ts_rec["address"], state=colored("FOUND", "green")
                )
            )
        else:
            ip = ipaddress.ip_address(ts_rec["address"])
            if isValidDNSRecord(ts_rec["hostname"]):
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
                    ts_rec["hostname"],
                    records_typemap[ip.version],
                    ts_rec["address"],
                    subdomain=config["cf-sub"],
                    zoneId=cf_ZoneId,
                )
            else:
                print(
                    '[{state}]: {host}.{tld} -> {ip} -> (Hostname: "{host}.{tld}" is not valid)'.format(
                        host=ts_rec["hostname"],
                        ip=ts_rec["address"],
                        state=colored("SKIPING", "red"),
                        tld=config["cf-domain"],
                    )
                )

        # Create IPv4-only subdomain records if configured
        if config.get("cf-sub-ipv4") and ip.version == 4:
            ipv4_sub = "." + config.get("cf-sub-ipv4").lower()
            ipv4_fqdn = (
                ts_rec["hostname"].lower() + ipv4_sub + "." + config["cf-domain"]
            )

            if any(
                c["name"] == ipv4_fqdn and c["content"] == ts_rec["address"]
                for c in cf_recordes
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
                    ts_rec["hostname"],
                    "A",
                    ts_rec["address"],
                    subdomain=config["cf-sub-ipv4"],
                    zoneId=cf_ZoneId,
                )

        # Create IPv6-only subdomain records if configured
        if config.get("cf-sub-ipv6") and ip.version == 6:
            ipv6_sub = "." + config.get("cf-sub-ipv6").lower()
            ipv6_fqdn = (
                ts_rec["hostname"].lower() + ipv6_sub + "." + config["cf-domain"]
            )

            if any(
                c["name"] == ipv6_fqdn and c["content"] == ts_rec["address"]
                for c in cf_recordes
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
                    ts_rec["hostname"],
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
        if config.get("cf-sub"):
            sub = "." + config.get("cf-sub").lower()
        else:
            sub = ""
        cf_name = cf_rec["name"].rsplit(sub + "." + config["cf-domain"], 1)[0]

        # Check if this is an IPv4-only subdomain record
        if config.get("cf-sub-ipv4"):
            ipv4_sub = "." + config.get("cf-sub-ipv4").lower()
            if cf_rec["name"].endswith(ipv4_sub + "." + config["cf-domain"]):
                cf_name = cf_rec["name"].rsplit(
                    ipv4_sub + "." + config["cf-domain"], 1
                )[0]
                sub = ipv4_sub
        # Check if this is an IPv6-only subdomain record
        elif config.get("cf-sub-ipv6"):
            ipv6_sub = "." + config.get("cf-sub-ipv6").lower()
            if cf_rec["name"].endswith(ipv6_sub + "." + config["cf-domain"]):
                cf_name = cf_rec["name"].rsplit(
                    ipv6_sub + "." + config["cf-domain"], 1
                )[0]
                sub = ipv6_sub
        # Check if this is the main dual-stack subdomain record
        elif cf_rec["name"].endswith(sub.lower() + "." + config["cf-domain"]):
            pass
        else:
            # Skip records that don't match any of our subdomains
            continue

        # Ignore any records not matching our prefix/postfix
        if not cf_name.startswith(config.get("prefix", "")):
            continue
        if not cf_name.endswith(config.get("postfix", "")):
            continue

        if any(
            a["hostname"] == cf_name and a["address"] == cf_rec["content"]
            for a in ts_records
        ):
            print(
                "[{state}]: {host} -> {ip}".format(
                    host=cf_rec["name"],
                    ip=cf_rec["content"],
                    state=colored("IN USE", "green"),
                )
            )
        else:
            if not isTailscaleIP(cf_rec["content"]):
                print(
                    "[{state}]: {host} -> {ip} (IP does not belong to a tailscale host. please remove manualy)".format(
                        host=cf_rec["name"],
                        ip=cf_rec["content"],
                        state=colored("SKIP DELETE", "red"),
                    )
                )
                continue

            print(
                "[{state}]: {host} -> {ip}".format(
                    host=cf_rec["name"],
                    ip=cf_rec["content"],
                    state=colored("DELETING", "yellow"),
                )
            )
            deleteDNSRecord(
                config["cf-key"], config["cf-domain"], cf_rec["id"], zoneId=cf_ZoneId
            )


if __name__ == "__main__":
    main()

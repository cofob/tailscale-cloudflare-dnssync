import ipaddress
import logging
import time

from cloudflare import (
    createDNSRecord,
    deleteDNSRecord,
    getZoneId,
    getZoneRecords,
    isValidDNSRecord,
)
from config import getConfig
from tailscale import cleanHostname, getTailscaleDevice, isTailscaleIP

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 5 * 60
CLEANUP_INTERVAL_SECONDS = 60 * 60


def get_ts_records(config: dict[str, str]) -> list[dict[str, str]]:
    if config["mode"] == "tailscale":
        return getTailscaleDevice(
            config["ts-key"],
            config["ts-client-id"],
            config["ts-client-secret"],
            config["ts-tailnet"],
        )
    if config["mode"] == "headscale":
        from headscale import getHeadscaleDevice

        return getHeadscaleDevice(config["hs-apikey"], config["hs-baseurl"])
    raise ValueError(f"unsupported mode: {config['mode']}")


def sync_records(config: dict[str, str], cf_zone_id: str, ts_records: list[dict[str, str]]) -> None:
    cf_records = getZoneRecords(config["cf-key"], config["cf-domain"], zoneId=cf_zone_id)
    records_typemap = {4: "A", 6: "AAAA"}

    logger.info("Adding new devices:")
    for ts_rec in ts_records:
        hostname_clean = cleanHostname(ts_rec["hostname"]) if ts_rec.get("hostname") else ""
        if not hostname_clean:
            logger.warning(
                "[%s]: %s -> (empty after cleanup, skipping)",
                "SKIPPING",
                ts_rec.get("hostname", ""),
            )
            continue

        cf_sub = config.get("cf-sub") or ""
        sub = "." + cf_sub.lower() if cf_sub else ""
        tsfqdn = hostname_clean + sub + "." + config["cf-domain"]
        ip = ipaddress.ip_address(ts_rec["address"])

        if any(c["name"] == tsfqdn and c["content"] == ts_rec["address"] for c in cf_records):
            logger.info("[%s]: %s -> %s", "FOUND", tsfqdn, ts_rec["address"])
        elif isValidDNSRecord(hostname_clean):
            logger.info("[%s]: %s -> %s", "ADDING", tsfqdn, ts_rec["address"])
            createDNSRecord(
                config["cf-key"],
                config["cf-domain"],
                hostname_clean,
                records_typemap[ip.version],
                ts_rec["address"],
                subdomain=config["cf-sub"],
                zoneId=cf_zone_id,
            )
        else:
            logger.warning(
                '[%s]: %s.%s -> %s -> (Hostname: "%s.%s" is not valid)',
                "SKIPPING",
                hostname_clean,
                config["cf-domain"],
                ts_rec["address"],
                hostname_clean,
                config["cf-domain"],
            )

        if config.get("cf-sub-ipv4") and ip.version == 4:
            ipv4_raw = config.get("cf-sub-ipv4") or ""
            ipv4_sub = "." + ipv4_raw.lower()
            ipv4_fqdn = hostname_clean + ipv4_sub + "." + config["cf-domain"]

            if any(c["name"] == ipv4_fqdn and c["content"] == ts_rec["address"] for c in cf_records):
                logger.info("[%s]: %s -> %s", "FOUND", ipv4_fqdn, ts_rec["address"])
            else:
                logger.info("[%s]: %s -> %s", "ADDING", ipv4_fqdn, ts_rec["address"])
                createDNSRecord(
                    config["cf-key"],
                    config["cf-domain"],
                    hostname_clean,
                    "A",
                    ts_rec["address"],
                    subdomain=config["cf-sub-ipv4"],
                    zoneId=cf_zone_id,
                )

        if config.get("cf-sub-ipv6") and ip.version == 6:
            ipv6_raw = config.get("cf-sub-ipv6") or ""
            ipv6_sub = "." + ipv6_raw.lower()
            ipv6_fqdn = hostname_clean + ipv6_sub + "." + config["cf-domain"]

            if any(c["name"] == ipv6_fqdn and c["content"] == ts_rec["address"] for c in cf_records):
                logger.info("[%s]: %s -> %s", "FOUND", ipv6_fqdn, ts_rec["address"])
            else:
                logger.info("[%s]: %s -> %s", "ADDING", ipv6_fqdn, ts_rec["address"])
                createDNSRecord(
                    config["cf-key"],
                    config["cf-domain"],
                    hostname_clean,
                    "AAAA",
                    ts_rec["address"],
                    subdomain=config["cf-sub-ipv6"],
                    zoneId=cf_zone_id,
                )


def cleanup_records(config: dict[str, str], cf_zone_id: str, ts_records: list[dict[str, str]]) -> None:
    logger.info("Cleaning up old records:")
    cf_records = getZoneRecords(config["cf-key"], config["cf-domain"], zoneId=cf_zone_id)

    normalized_ts_records: list[dict[str, str]] = []
    for ts_rec in ts_records:
        hostname_clean = cleanHostname(ts_rec.get("hostname", "")).lower()
        if not hostname_clean:
            continue
        normalized_ts_records.append({"hostname": hostname_clean, "address": ts_rec["address"]})

    for cf_rec in cf_records:
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
            continue

        if not cf_name.startswith(config.get("prefix", "")):
            continue
        if not cf_name.endswith(config.get("postfix", "")):
            continue

        if any(
            a["hostname"] == cf_name and a["address"] == cf_rec["content"]
            for a in normalized_ts_records
        ):
            logger.info("[%s]: %s -> %s", "IN USE", cf_rec["name"], cf_rec["content"])
        else:
            if not isTailscaleIP(cf_rec["content"]):
                logger.warning(
                    "[%s]: %s -> %s (IP does not belong to a tailscale host. please remove manualy)",
                    "SKIP DELETE",
                    cf_rec["name"],
                    cf_rec["content"],
                )
                continue

            logger.info("[%s]: %s -> %s", "DELETING", cf_rec["name"], cf_rec["content"])
            deleteDNSRecord(config["cf-key"], config["cf-domain"], cf_rec["id"], zoneId=cf_zone_id)


def main() -> None:
    config = getConfig()
    cf_zone_id = getZoneId(config["cf-key"], config["cf-domain"])
    logger.info("running in %s mode", config["mode"])
    logger.info(
        "poll intervals: sync=%ss cleanup=%ss",
        SYNC_INTERVAL_SECONDS,
        CLEANUP_INTERVAL_SECONDS,
    )

    ts_records = get_ts_records(config)
    sync_records(config, cf_zone_id, ts_records)
    cleanup_records(config, cf_zone_id, ts_records)

    next_sync = time.monotonic() + SYNC_INTERVAL_SECONDS
    next_cleanup = time.monotonic() + CLEANUP_INTERVAL_SECONDS
    last_ts_records = ts_records

    while True:
        now = time.monotonic()

        if now >= next_sync:
            try:
                last_ts_records = get_ts_records(config)
                sync_records(config, cf_zone_id, last_ts_records)
            except SystemExit as exc:
                logger.error("sync cycle failed: %s", exc)
            while next_sync <= now:
                next_sync += SYNC_INTERVAL_SECONDS

        if now >= next_cleanup:
            try:
                cleanup_records(config, cf_zone_id, last_ts_records)
            except SystemExit as exc:
                logger.error("cleanup cycle failed: %s", exc)
            while next_cleanup <= now:
                next_cleanup += CLEANUP_INTERVAL_SECONDS

        sleep_for = max(1.0, min(next_sync, next_cleanup) - time.monotonic())
        time.sleep(sleep_for)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        main()
    except KeyboardInterrupt:
        logger.info("shutdown requested")

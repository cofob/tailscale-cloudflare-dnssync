import ipaddress
import json
import logging
import hmac
import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

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
WEBHOOK_DEFAULT_LISTEN = "0.0.0.0"
WEBHOOK_DEFAULT_PORT = 8080
WEBHOOK_DEFAULT_PATH = "/tailscale/webhook"
WEBHOOK_DEFAULT_MAX_AGE_SECONDS = 300


class WebhookSettings:
    def __init__(self, listen: str, port: int, path: str, secret: str, max_age_seconds: int):
        self.listen = listen
        self.port = port
        self.path = path
        self.secret = secret
        self.max_age_seconds = max_age_seconds


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


def parse_bool(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def parse_webhook_settings(config: dict[str, str]) -> Optional[WebhookSettings]:
    enabled = parse_bool(config.get("ts-webhook-enabled", ""))
    if not enabled:
        return None

    secret = (config.get("ts-webhook-secret") or "").strip()
    if not secret:
        logger.error("ts-webhook-enabled=true requires ts-webhook-secret")
        raise SystemExit(1)

    listen = (config.get("ts-webhook-listen") or WEBHOOK_DEFAULT_LISTEN).strip()
    path = (config.get("ts-webhook-path") or WEBHOOK_DEFAULT_PATH).strip()
    if not path.startswith("/"):
        path = "/" + path

    try:
        port = int((config.get("ts-webhook-port") or str(WEBHOOK_DEFAULT_PORT)).strip())
    except ValueError as exc:
        logger.error("invalid ts-webhook-port: %s", exc)
        raise SystemExit(1) from exc

    try:
        max_age_seconds = int(
            (config.get("ts-webhook-max-age-seconds") or str(WEBHOOK_DEFAULT_MAX_AGE_SECONDS)).strip()
        )
    except ValueError as exc:
        logger.error("invalid ts-webhook-max-age-seconds: %s", exc)
        raise SystemExit(1) from exc

    return WebhookSettings(
        listen=listen,
        port=port,
        path=path,
        secret=secret,
        max_age_seconds=max_age_seconds,
    )


def verify_webhook_signature(
    signature_header: str,
    secret: str,
    body: bytes,
    max_age_seconds: int,
) -> bool:
    parts: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        key, sep, value = part.strip().partition("=")
        if sep and key and value:
            parts.setdefault(key, []).append(value)

    ts_values = parts.get("t", [])
    sig_v1_values = parts.get("v1", [])
    if not ts_values or not sig_v1_values:
        return False

    try:
        ts = int(ts_values[0])
    except ValueError:
        return False

    if abs(int(time.time()) - ts) > max_age_seconds:
        return False

    payload = str(ts).encode("utf-8") + b"." + body
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in sig_v1_values)


def create_webhook_handler(
    settings: WebhookSettings,
    request_sync: threading.Event,
) -> type[BaseHTTPRequestHandler]:
    class TailscaleWebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path != settings.path:
                self.send_response(404)
                self.end_headers()
                return

            signature_header = self.headers.get("Tailscale-Webhook-Signature", "")
            content_length_raw = self.headers.get("Content-Length", "0")
            try:
                content_length = int(content_length_raw)
            except ValueError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"invalid content length")
                return

            body = self.rfile.read(content_length)
            if not verify_webhook_signature(
                signature_header=signature_header,
                secret=settings.secret,
                body=body,
                max_age_seconds=settings.max_age_seconds,
            ):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"invalid signature")
                return

            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"invalid json")
                return

            event_types: list[str] = []
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        event_type = item.get("type")
                        if isinstance(event_type, str):
                            event_types.append(event_type)
            elif isinstance(payload, dict):
                event_type = payload.get("type")
                if isinstance(event_type, str):
                    event_types.append(event_type)

            logger.info("webhook accepted, events=%s", ",".join(event_types) if event_types else "unknown")
            request_sync.set()
            self.send_response(202)
            self.end_headers()
            self.wfile.write(b"accepted")

        def log_message(self, fmt: str, *args: object) -> None:
            logger.debug("webhook_http: " + fmt, *args)

    return TailscaleWebhookHandler


def start_webhook_server(
    settings: WebhookSettings,
    request_sync: threading.Event,
) -> ThreadingHTTPServer:
    handler = create_webhook_handler(settings, request_sync)
    server = ThreadingHTTPServer((settings.listen, settings.port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="tailscale-webhook")
    thread.start()
    logger.info(
        "webhook listener enabled at http://%s:%s%s",
        settings.listen,
        settings.port,
        settings.path,
    )
    return server


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
    webhook_settings = parse_webhook_settings(config)
    sync_requested = threading.Event()
    webhook_server = None
    if webhook_settings:
        if config["mode"] != "tailscale":
            logger.warning("webhook listener is only supported in tailscale mode; disabled")
        else:
            webhook_server = start_webhook_server(webhook_settings, sync_requested)

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

    try:
        while True:
            now = time.monotonic()

            if sync_requested.is_set():
                sync_requested.clear()
                try:
                    last_ts_records = get_ts_records(config)
                    sync_records(config, cf_zone_id, last_ts_records)
                except SystemExit as exc:
                    logger.error("webhook-triggered sync failed: %s", exc)
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
            sync_requested.wait(timeout=sleep_for)
    finally:
        if webhook_server:
            webhook_server.shutdown()
            webhook_server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        main()
    except KeyboardInterrupt:
        logger.info("shutdown requested")

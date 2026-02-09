import configparser
import logging
import os
import os.path
import sys

logger = logging.getLogger(__name__)

keysToImport = ["cf-key", "cf-domain", "ts-tailnet"]
keysOptional = [
    "cf-sub",
    "cf-sub-ipv4",
    "cf-sub-ipv6",
    "prefix",
    "postfix",
    "ts-key",
    "ts-client-id",
    "ts-client-secret",
    "ts-tag-filter",
    "mode",
    "hs-baseurl",
    "hs-apikey",
]


def importkey(name: str, optional: bool = False) -> str:
    key = name
    envKey = key.replace("-", "_")

    secretPath = "/run/secrets/" + key
    if os.path.isfile(secretPath):
        with open(secretPath) as secret:
            return f"{secret.readline().strip()}"
    if key in os.environ:
        return os.environ.get(key, "")
    if envKey in os.environ:
        return os.environ.get(envKey, "")
    try:
        cfgPath = os.path.dirname(os.path.realpath(__file__)) + "/config.ini"
        with open(cfgPath) as _:
            config = configparser.ConfigParser()
            config.read(cfgPath)
            cfg = config["DEFAULT"]
    except Exception as e:
        logger.exception("could not read config file: %s", e)
        if optional:
            return ""
        sys.exit("could not read config file")
    try:
        return cfg[key]
    except KeyError:
        if optional:
            return ""
        logger.error("ERROR: mandatory configuration not found: %s", key)
        sys.exit(1)


def getConfig() -> dict[str, str]:
    # static = {
    #     'cf-key': '',
    #     'cf-domain': "".lower(),
    #     'ts-key': 'tskey-',
    #     'ts-tailnet': ''
    # }
    static: dict[str, str] = {}

    for key in keysToImport:
        static[key] = importkey(key)
    for key in keysOptional:
        static[key] = importkey(key, True)

    # check for tailscale config
    if static["mode"] == "" or static["mode"] == "tailscale":
        static["mode"] = "tailscale"
        if not static["ts-key"] and not (static["ts-client-id"] and static["ts-client-secret"]):
            logger.error("ERROR: tailscale config missing: ts-key or ts-client-id/ts-client-secret")
            sys.exit(1)
    # check for headscale Config
    if static["mode"] == "headscale" and not (static["hs-baseurl"] and static["hs-apikey"]):
        logger.error("ERROR: headscale config missing: hs-baseurl and/or hs-apikey")
        sys.exit(1)
    # unkown mode unfigured
    if static["mode"] not in ["", "tailscale", "headscale"]:
        logger.error("ERROR: unknown mode configured (got: %s)", static["mode"])
        sys.exit(1)

    return static


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info(getConfig())

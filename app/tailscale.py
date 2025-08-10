import ipaddress
import json
import re
import sys

import requests
from config import getConfig
from oauthlib.oauth2 import BackendApplicationClient
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from termcolor import colored


### Get Data
def getTailscaleDevice(
    apikey: str, clientid: str, clientsecret: str, tailnet: str
) -> list[dict[str, str]]:
    if apikey:
        apikey = apikey.strip()
    if clientid:
        clientid = clientid.strip()
    if clientsecret:
        clientsecret = clientsecret.strip()
    if clientid and clientsecret:
        token = OAuth2Session(client=BackendApplicationClient(client_id=clientid)).fetch_token(
            token_url="https://api.tailscale.com/api/v2/oauth/token",
            client_id=clientid,
            client_secret=clientsecret,
        )
        apikey = token["access_token"]
    url = f"https://api.tailscale.com/api/v2/tailnet/{tailnet}/devices"
    payload: dict[str, str] = {}
    headers: dict[str, str] = {}
    response = requests.request(
        "GET",
        url,
        headers=headers,
        data=payload,
        auth=HTTPBasicAuth(username=apikey, password=""),
    )
    # print(response.text)
    # print(json.dumps(json.loads(response.text), indent=2))

    output: list[dict[str, str]] = []

    data = json.loads(response.text)
    if response.status_code == 200:
        output = []
        config = getConfig()
        tag_filter_raw = config.get("ts-tag-filter", "")
        tag_filters = set(
            [
                (
                    t.strip().lower()
                    if t.strip().lower().startswith("tag:")
                    else f"tag:{t.strip().lower()}"
                )
                for t in tag_filter_raw.split(",")
                if t.strip() != ""
            ]
        )

        for device in data["devices"]:
            device_tags = {t.lower() for t in device.get("tags", [])}
            if tag_filters and device_tags.isdisjoint(tag_filters):
                # include device only if at least one tag matches
                continue

            base_name = device["name"].split(".")[0].lower()
            for address in device["addresses"]:
                output.append({"hostname": alterHostname(base_name), "address": address})
        return output
    sys.exit(
        colored(
            "getTailscaleDevice() - {status}, {error}".format(
                status=str(response.status_code), error=data.get("message", "")
            ),
            "red",
        )
    )


def isTailscaleIP(ip: str) -> bool:
    parsed_ip = ipaddress.ip_address(ip)

    if parsed_ip.version == 6:
        return parsed_ip in ipaddress.IPv6Network("fd7a:115c:a1e0::/48")
    if parsed_ip.version == 4:
        return parsed_ip in ipaddress.IPv4Network("100.64.0.0/10")
    sys.exit("isTailscaleIP(): - unknown IP version")


def alterHostname(hostname: str) -> str:
    config = getConfig()
    pre = config.get("prefix", "")
    post = config.get("postfix", "")

    cleaned_base = cleanHostname(hostname)
    new_hostname = f"{pre}{cleaned_base}{post}"
    # Clean again to ensure pre/postfix did not introduce invalid chars
    return cleanHostname(new_hostname)


def cleanHostname(hostname: str) -> str:
    # lowercase and strip whitespace
    hn = (hostname or "").strip().lower()
    # replace spaces and underscores with hyphens
    hn = hn.replace(" ", "-").replace("_", "-")
    # remove any character not a-z, 0-9, dash or dot
    hn = re.sub(r"[^a-z0-9\-.]", "", hn)
    # collapse multiple dashes
    hn = re.sub(r"-+", "-", hn)
    # strip leading/trailing dashes and dots
    return hn.strip("-.")

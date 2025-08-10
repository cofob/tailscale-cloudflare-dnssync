import ipaddress
import json  # type: ignore
import re

import requests
from config import getConfig
from oauthlib.oauth2 import BackendApplicationClient  # type: ignore
from requests.auth import HTTPBasicAuth  # type: ignore
from requests_oauthlib import OAuth2Session  # type: ignore
from termcolor import colored  # type: ignore


### Get Data
def getTailscaleDevice(apikey, clientid, clientsecret, tailnet):
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
    payload = {}
    headers = {}
    response = requests.request(
        "GET",
        url,
        headers=headers,
        data=payload,
        auth=HTTPBasicAuth(username=apikey, password=""),
    )
    # print(response.text)
    # print(json.dumps(json.loads(response.text), indent=2))

    output = []

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
            device_tags = set([t.lower() for t in device.get("tags", [])])
            if tag_filters:
                # include device only if at least one tag matches
                if device_tags.isdisjoint(tag_filters):
                    continue

            base_name = device["name"].split(".")[0].lower()
            for address in device["addresses"]:
                output.append({"hostname": alterHostname(base_name), "address": address})
        return output
    else:
        exit(
            colored(
                "getTailscaleDevice() - {status}, {error}".format(
                    status=str(response.status_code), error=data["message"]
                ),
                "red",
            )
        )


def isTailscaleIP(ip):
    ip = ipaddress.ip_address(ip)

    if ip.version == 6:
        if ip in ipaddress.IPv6Network("fd7a:115c:a1e0::/48"):
            return True
        else:
            return False
    elif ip.version == 4:
        if ip in ipaddress.IPv4Network("100.64.0.0/10"):
            return True
        else:
            return False
    else:
        exit("isTailscaleIP(): - unknown IP version")


def alterHostname(hostname):
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
    hn = hn.strip("-.")
    return hn

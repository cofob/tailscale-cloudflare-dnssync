import json
import re
import sys
from typing import Any, Optional

import requests
from termcolor import colored, cprint


def getZoneId(token: str, domain: str) -> str:
    url = "https://api.cloudflare.com/client/v4/zones"
    payload: dict[str, str] = {}
    headers = {"Authorization": f"Bearer {token.strip()}"}
    response = requests.request("GET", url, headers=headers, data=payload)
    data = json.loads(response.text)

    if data["success"]:
        for zone in data["result"]:
            if zone["name"] == domain:
                return str(zone["id"])
        sys.exit(colored(f'getZoneId(): domain "{domain}" not found', "red"))

    sys.exit(colored("getZoneId(): " + json.dumps(data["errors"], indent=2), "red"))


def getZoneRecords(token: str, domain: str, zoneId: Optional[str] = None) -> list[dict[str, Any]]:
    if zoneId:
        url = f"https://api.cloudflare.com/client/v4/zones/{zoneId}/dns_records?per_page=150"
    else:
        zid = getZoneId(token, domain)
        url = f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records?per_page=150"
    payload: dict[str, str] = {}
    headers = {"Authorization": f"Bearer {token.strip()}"}

    response = requests.request("GET", url, headers=headers, data=payload)
    data = json.loads(response.text)

    output: list[dict[str, Any]] = []

    if data["success"]:
        for record in data["result"]:
            if record["type"] in ["A", "AAAA"]:
                output.append(record)
        return output

    sys.exit(
        colored(
            "getZoneRecords() - error\n{}".format(json.dumps(data["errors"], indent=2)),
            "red",
        )
    )


def createDNSRecord(
    token: str,
    domain: str,
    name: str,
    record_type: str,
    content: str,
    subdomain: Optional[str] = None,
    zoneId: Optional[str] = None,
    ttl: int = 120,
) -> bool:
    if zoneId:
        url = f"https://api.cloudflare.com/client/v4/zones/{zoneId}/dns_records"
    else:
        zid = getZoneId(token, domain)
        url = f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records"
    fqdn = name + "." + subdomain + "." + domain if subdomain else name + "." + domain

    payload: dict[str, Any] = {
        "type": record_type,
        "name": fqdn,
        "content": content,
        "ttl": ttl,
        "comment": "@managed by auto-sync script",
    }
    headers = {"Authorization": f"Bearer {token.strip()}"}

    response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
    data = json.loads(response.text)

    if data["success"]:
        print(
            "--> [CLOUDFLARE] [{code}] {msg}".format(
                code=response.status_code, msg=colored("record created", "green")
            )
        )
        return True

    cprint("[ERROR]", "red")
    sys.exit("createDNSRecord():  " + json.dumps(data["errors"], indent=2))


def deleteDNSRecord(token: str, domain: str, record_id: str, zoneId: Optional[str] = None) -> None:
    if zoneId:
        url = f"https://api.cloudflare.com/client/v4/zones/{zoneId}/dns_records/{record_id}"
    else:
        zid = getZoneId(token, domain)
        url = f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records/{record_id}"
    headers = {"Authorization": f"Bearer {token.strip()}"}
    response = requests.request("DELETE", url, headers=headers)
    print(
        "--> [CLOUDFLARE] [{code}] {msg}".format(
            code=response.status_code, msg=colored("record deleted", "green")
        )
    )


def isValidDNSRecord(name: str) -> bool:
    regex = r"^([a-zA-Z]|\d|-|\.)*$"
    return re.match(regex, name) is not None


if __name__ == "__main__":
    token = ""
    domain = ""
    print(getZoneId(token, domain))
    print(json.dumps(getZoneRecords(token, domain), indent=2))

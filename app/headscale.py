import json
import logging
import sys

import requests
from tailscale import alterHostname

logger = logging.getLogger(__name__)


def getHeadscaleDevice(apikey: str, baseurl: str) -> list[dict[str, str]]:
    url = f"{baseurl}/api/v1/machine"
    payload: dict[str, str] = {}
    headers = {"Authorization": f"Bearer {apikey}"}
    response = requests.request("GET", url, headers=headers, data=payload)

    output: list[dict[str, str]] = []

    data = json.loads(response.text)
    if response.status_code == 200:
        output = []
        for device in data["machines"]:
            for address in device["ipAddresses"]:
                if not device["givenName"].lower().startswith("localhost"):
                    output.append(
                        {
                            "hostname": alterHostname(device["givenName"].split(".")[0].lower()),
                            "address": address,
                        }
                    )
        return output
    logger.error(
        "getTailscaleDevice() - %s, %s",
        str(response.status_code),
        data.get("message", ""),
    )
    sys.exit(1)

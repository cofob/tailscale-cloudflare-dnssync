import json

import requests
from tailscale import alterHostname
from termcolor import colored


def getHeadscaleDevice(apikey, baseurl):
    url = f"{baseurl}/api/v1/machine"
    payload = {}
    headers = {"Authorization": f"Bearer {apikey}"}
    response = requests.request("GET", url, headers=headers, data=payload)

    output = []

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
    else:
        exit(
            colored(
                "getTailscaleDevice() - {status}, {error}".format(
                    status=str(response.status_code), error=data["message"]
                ),
                "red",
            )
        )

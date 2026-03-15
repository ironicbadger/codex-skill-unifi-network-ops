#!/usr/bin/env python3
"""Read-only Site Manager probe for UniFi accounts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List UniFi sites from the Site Manager API and optionally enrich them with host details."
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UNIFI_SITE_MANAGER_API_KEY"),
        help="UniFi Site Manager API key. Defaults to UNIFI_SITE_MANAGER_API_KEY.",
    )
    parser.add_argument(
        "--base-url",
        default="https://api.ui.com/v1",
        help="Base URL for the official Site Manager API.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Page size for paginated list requests.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--include-host-details",
        action="store_true",
        help="Fetch /hosts/{id} for each host referenced by the returned sites.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of a compact text summary.",
    )
    return parser.parse_args()


def build_url(base_url: str, path: str, params: dict[str, str | int | None] | None = None) -> str:
    url = base_url.rstrip("/") + path
    if params:
        filtered = {key: value for key, value in params.items() if value is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered)
    return url


def request_json(url: str, api_key: str, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail = body
        try:
            parsed = json.loads(body)
            detail = json.dumps(parsed, indent=2, sort_keys=True)
        except json.JSONDecodeError:
            pass
        raise SystemExit(f"HTTP {exc.code} for {url}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc.reason}") from exc


def list_sites(base_url: str, api_key: str, page_size: int, timeout: int) -> list[dict]:
    sites: list[dict] = []
    next_token: str | None = None

    while True:
        payload = request_json(
            build_url(
                base_url,
                "/sites",
                {
                    "pageSize": page_size,
                    "nextToken": next_token,
                },
            ),
            api_key,
            timeout,
        )
        sites.extend(payload.get("data", []))
        next_token = payload.get("nextToken")
        if not next_token:
            return sites


def get_host(base_url: str, api_key: str, host_id: str, timeout: int) -> dict:
    payload = request_json(
        build_url(base_url, f"/hosts/{urllib.parse.quote(host_id, safe='')}"),
        api_key,
        timeout,
    )
    return payload.get("data", {})


def summarize_site(site: dict, host: dict | None) -> str:
    meta = site.get("meta", {})
    stats = site.get("statistics", {})
    counts = stats.get("counts", {})
    isp = stats.get("ispInfo", {})
    percentages = stats.get("percentages", {})
    host_bits = []
    if host:
        host_bits.append(f"host_type={host.get('type', 'unknown')}")
        host_bits.append(f"host_ip={host.get('ipAddress', 'unknown')}")
        host_bits.append(f"host_blocked={host.get('isBlocked', 'unknown')}")

    fields = [
        f"site={meta.get('name', site.get('siteId', 'unknown'))}",
        f"site_id={site.get('siteId', 'unknown')}",
        f"host_id={site.get('hostId', 'unknown')}",
        f"permission={site.get('permission', 'unknown')}",
        f"owner={site.get('isOwner', 'unknown')}",
        f"devices={counts.get('totalDevice', 'unknown')}",
        f"offline_devices={counts.get('offlineDevice', 'unknown')}",
        f"wifi_clients={counts.get('wifiClient', 'unknown')}",
        f"wired_clients={counts.get('wiredClient', 'unknown')}",
        f"wan_uptime={percentages.get('wanUptime', 'unknown')}",
        f"isp={isp.get('name', 'unknown')}",
    ]
    fields.extend(host_bits)
    return " | ".join(fields)


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "Missing API key. Pass --api-key or set UNIFI_SITE_MANAGER_API_KEY."
        )

    sites = list_sites(args.base_url, args.api_key, args.page_size, args.timeout)
    hosts: dict[str, dict] = {}

    if args.include_host_details:
        host_ids = sorted({site.get("hostId") for site in sites if site.get("hostId")})
        for host_id in host_ids:
            hosts[host_id] = get_host(args.base_url, args.api_key, host_id, args.timeout)

    if args.json:
        json.dump(
            {
                "sites": sites,
                "hosts": hosts,
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return

    if not sites:
        print("No sites returned.")
        return

    for site in sites:
        host = hosts.get(site.get("hostId"))
        print(summarize_site(site, host))


if __name__ == "__main__":
    main()

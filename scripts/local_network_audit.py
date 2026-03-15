#!/usr/bin/env python3
"""Read-only local UniFi Network API audit with Wi-Fi baseline checks."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SENSITIVE_KEYS = {"passphrase", "password", "presharedkey", "token", "secret", "x-api-key"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit a local UniFi site through the official local Network API."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("UNIFI_HOST")
        or os.environ.get("UNIFI_UI_URL")
        or "https://unifi",
        help="Local UniFi host. Defaults to UNIFI_HOST, then UNIFI_UI_URL, then https://unifi.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UNIFI_NETWORK_API_KEY"),
        help="Local UniFi Network API key. Defaults to UNIFI_NETWORK_API_KEY.",
    )
    parser.add_argument(
        "--site-id",
        default=os.environ.get("UNIFI_SITE_ID"),
        help="Site ID. If omitted, resolve by --site-name.",
    )
    parser.add_argument(
        "--site-name",
        default=os.environ.get("UNIFI_SITE_NAME") or "default",
        help="Site internal reference or display name when --site-id is omitted.",
    )
    parser.add_argument(
        "--base-path",
        default="/proxy/network/integration/v1",
        help="Base path for the local UniFi Network API.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Page size for paginated list endpoints.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS verification. Useful for IP-based local URLs with self-signed certs.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a redacted structured JSON report.",
    )
    return parser.parse_args()


def normalize_host(host: str) -> str:
    parsed = urllib.parse.urlparse(host)
    if parsed.scheme:
        return host.rstrip("/")
    return "https://" + host.rstrip("/")


def build_url(host: str, base_path: str, path: str, params: dict[str, str | int] | None = None) -> str:
    url = host.rstrip("/") + "/" + base_path.strip("/") + path
    if params:
        filtered = {key: value for key, value in params.items() if value is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered)
    return url


def make_opener(insecure: bool) -> urllib.request.OpenerDirector:
    if not insecure:
        return urllib.request.build_opener()
    context = ssl._create_unverified_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))


def request_json(opener: urllib.request.OpenerDirector, url: str, api_key: str, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": api_key,
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail = body
        try:
            detail = json.dumps(json.loads(body), indent=2, sort_keys=True)
        except json.JSONDecodeError:
            pass
        raise SystemExit(f"HTTP {exc.code} for {url}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc.reason}") from exc


def list_collection(
    opener: urllib.request.OpenerDirector,
    host: str,
    base_path: str,
    path: str,
    api_key: str,
    timeout: int,
    page_size: int,
) -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        payload = request_json(
            opener,
            build_url(host, base_path, path, {"offset": offset, "limit": page_size}),
            api_key,
            timeout,
        )
        page_items = payload.get("data", [])
        items.extend(page_items)
        count = payload.get("count", len(page_items))
        total_count = payload.get("totalCount", len(page_items))
        if not page_items or len(items) >= total_count or count < page_size:
            return items
        offset += count


def get_item(
    opener: urllib.request.OpenerDirector,
    host: str,
    base_path: str,
    path: str,
    api_key: str,
    timeout: int,
) -> dict:
    return request_json(opener, build_url(host, base_path, path), api_key, timeout)


def resolve_site(site_list: list[dict], site_id: str | None, site_name: str) -> dict:
    if site_id:
        for site in site_list:
            if site.get("id") == site_id:
                return site
        raise SystemExit(f"Site ID {site_id} not found.")

    lowered = site_name.lower()
    for site in site_list:
        if site.get("internalReference", "").lower() == lowered or site.get("name", "").lower() == lowered:
            return site
    available = ", ".join(sorted(filter(None, {site.get("internalReference") or site.get("name") for site in site_list})))
    raise SystemExit(f"Site {site_name!r} not found. Available sites: {available}")


def redact(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def subnet_for_network(network: dict) -> str | None:
    config = network.get("ipv4Configuration", {})
    host_ip = config.get("hostIpAddress")
    prefix_length = config.get("prefixLength")
    if not host_ip or prefix_length is None:
        return None
    try:
        return str(ipaddress.ip_network(f"{host_ip}/{prefix_length}", strict=False))
    except ValueError:
        return None


def network_reference_counts(reference_payload: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for resource in reference_payload.get("referenceResources", []):
        counts[resource.get("resourceType", "UNKNOWN")] = resource.get("referenceCount", 0)
    return counts


def summarize_wifi(ssid: dict, networks_by_id: dict[str, dict]) -> dict:
    security = ssid.get("securityConfiguration", {})
    mappings: list[str] = []
    if ssid.get("network", {}).get("type") == "NATIVE":
        mappings.append("native")
    elif ssid.get("network", {}).get("networkId"):
        mappings.append(networks_by_id.get(ssid["network"]["networkId"], {}).get("name", ssid["network"]["networkId"]))
    for key in security.get("presharedKeys", []):
        network = key.get("network", {})
        if network.get("type") == "NATIVE":
            mappings.append("native")
        elif network.get("networkId"):
            mappings.append(networks_by_id.get(network["networkId"], {}).get("name", network["networkId"]))

    return {
        "id": ssid.get("id"),
        "name": ssid.get("name"),
        "enabled": ssid.get("enabled"),
        "frequencies_ghz": ssid.get("broadcastingFrequenciesGHz", []),
        "client_isolation": ssid.get("clientIsolationEnabled"),
        "network_mappings": sorted(dict.fromkeys(mappings)),
        "device_filter": ssid.get("broadcastingDeviceFilter"),
        "security_type": security.get("type"),
    }


def summarize_ap(device: dict, stats: dict) -> dict:
    radios = []
    retry_by_freq = {
        radio.get("frequencyGHz"): radio.get("txRetriesPct")
        for radio in stats.get("interfaces", {}).get("radios", [])
    }
    for radio in device.get("interfaces", {}).get("radios", []):
        freq = radio.get("frequencyGHz")
        radios.append(
            {
                "frequency_ghz": freq,
                "channel": radio.get("channel"),
                "channel_width_mhz": radio.get("channelWidthMHz"),
                "tx_retries_pct": retry_by_freq.get(freq),
            }
        )
    return {
        "id": device.get("id"),
        "name": device.get("name"),
        "model": device.get("model"),
        "state": device.get("state"),
        "radios": radios,
    }


def find_radio(ap: dict, frequency_ghz: float) -> dict | None:
    for radio in ap.get("radios", []):
        if radio.get("frequency_ghz") == frequency_ghz:
            return radio
    return None


def build_findings(
    networks: list[dict],
    wifi_details: list[dict],
    access_points: list[dict],
    zones: list[dict],
    policies: list[dict],
    acl_rules: list[dict],
    network_references: dict[str, dict],
) -> list[dict]:
    findings: list[dict] = []
    networks_by_id = {network["id"]: network for network in networks}
    zones_by_id = {zone["id"]: zone for zone in zones}

    primary_passphrases = {}
    for wifi in wifi_details:
        security = wifi.get("securityConfiguration", {})
        if security.get("passphrase"):
            primary_passphrases[wifi.get("name", "")] = security.get("passphrase")

    for wifi in wifi_details:
        name = wifi.get("name", "")
        lowered = name.lower()
        security = wifi.get("securityConfiguration", {})
        psks = security.get("presharedKeys", [])
        mappings = []
        has_native_mapping = False
        reused_primary = False

        for psk in psks:
            network = psk.get("network", {})
            if network.get("type") == "NATIVE":
                mappings.append("native")
                has_native_mapping = True
            elif network.get("networkId"):
                mappings.append(networks_by_id.get(network["networkId"], {}).get("name", network["networkId"]))
            if psk.get("passphrase") and psk["passphrase"] in primary_passphrases.values():
                reused_primary = True

        if "iot" in lowered and (len(set(mappings)) > 1 or has_native_mapping):
            findings.append(
                {
                    "severity": "high",
                    "domain": "wifi",
                    "message": f"SSID {name} maps clients into multiple trust domains, including the native LAN.",
                }
            )
        if "iot" in lowered and reused_primary:
            findings.append(
                {
                    "severity": "high",
                    "domain": "wifi",
                    "message": f"SSID {name} reuses a primary LAN preshared key, creating a second entry path into the main network.",
                }
            )

    isolated_networks = [network for network in networks if network.get("isolationEnabled")]
    shared_zone_ids = {network.get("zoneId") for network in isolated_networks if network.get("zoneId")}
    allow_all_pairs = {
        (policy.get("source", {}).get("zoneId"), policy.get("destination", {}).get("zoneId"))
        for policy in policies
        if policy.get("enabled")
        and policy.get("action", {}).get("type") == "ALLOW"
        and not policy.get("source", {}).get("trafficFilter")
        and not policy.get("destination", {}).get("trafficFilter")
    }
    source_filtered_block_subnets = set()
    for policy in policies:
        if policy.get("action", {}).get("type") != "BLOCK":
            continue
        source_filter = policy.get("source", {}).get("trafficFilter", {})
        ip_filter = source_filter.get("ipAddressFilter", {})
        for item in ip_filter.get("items", []):
            if item.get("type") == "SUBNET":
                source_filtered_block_subnets.add(item.get("value"))

    for zone_id in shared_zone_ids:
        zone_networks = [network for network in networks if network.get("zoneId") == zone_id]
        isolated_in_zone = [network for network in isolated_networks if network.get("zoneId") == zone_id]
        non_isolated_in_zone = [network for network in zone_networks if not network.get("isolationEnabled")]
        if not isolated_in_zone or not non_isolated_in_zone:
            continue
        zone_name = zones_by_id.get(zone_id, {}).get("name", zone_id)
        isolated_subnets = {subnet_for_network(network) for network in isolated_in_zone}
        if (zone_id, zone_id) in allow_all_pairs:
            names = ", ".join(sorted(network.get("name", "unknown") for network in isolated_in_zone))
            qualifier = "same-zone allow-all remains in place"
            if isolated_subnets & source_filtered_block_subnets:
                qualifier = "the system isolated-network block is source-based only"
            findings.append(
                {
                    "severity": "high",
                    "domain": "segmentation",
                    "message": f"Isolated networks {names} still share zone {zone_name}, so {qualifier}.",
                }
            )
            break

    for network in networks:
        counts = network_reference_counts(network_references[network["id"]])
        total_refs = sum(counts.values())
        if total_refs == 0:
            findings.append(
                {
                    "severity": "medium",
                    "domain": "segmentation",
                    "message": f"Network {network.get('name')} has no current Wi-Fi, client, or device references.",
                }
            )

    for policy in policies:
        if not policy.get("enabled"):
            continue
        source_zone = zones_by_id.get(policy.get("source", {}).get("zoneId", ""), {}).get("name", "")
        destination_zone = zones_by_id.get(policy.get("destination", {}).get("zoneId", ""), {}).get("name", "")
        if policy.get("name", "").startswith("Allow Return Traffic"):
            continue
        if source_zone == "External" and destination_zone == "Internal" and policy.get("action", {}).get("type") == "ALLOW":
            target_filter = policy.get("destination", {}).get("trafficFilter", {})
            ip_items = target_filter.get("ipAddressFilter", {}).get("items", [])
            port_items = target_filter.get("portFilter", {}).get("items", [])
            if not port_items:
                port_items = policy.get("source", {}).get("trafficFilter", {}).get("portFilter", {}).get("items", [])
            targets = ",".join(item.get("value", "?") for item in ip_items) or "internal target"
            ports = ",".join(str(item.get("value", "?")) for item in port_items) or "all ports"
            findings.append(
                {
                    "severity": "medium",
                    "domain": "firewall",
                    "message": f"External allow rule {policy.get('name')} exposes {targets} on {ports}.",
                }
            )

    if not acl_rules:
        findings.append(
            {
                "severity": "low",
                "domain": "firewall",
                "message": "No ACL rules are configured; segmentation depends entirely on zones, isolation flags, and firewall policies.",
            }
        )

    two_four_channels = []
    retry_hotspots = []
    for ap in access_points:
        radio24 = find_radio(ap, 2.4)
        if radio24 and radio24.get("channel") is not None:
            two_four_channels.append(radio24["channel"])
        for radio in ap.get("radios", []):
            if radio.get("tx_retries_pct") is not None and radio["tx_retries_pct"] >= 15:
                retry_hotspots.append(
                    f"{ap.get('name')} {radio.get('frequency_ghz')}GHz {radio.get('tx_retries_pct')}%"
                )

    counts = Counter(two_four_channels)
    duplicate_channels = sorted(channel for channel, count in counts.items() if count > 1)
    if duplicate_channels:
        findings.append(
            {
                "severity": "medium",
                "domain": "wifi",
                "message": f"2.4 GHz channel plan has duplicate assignments on channels {', '.join(map(str, duplicate_channels))}.",
            }
        )
    if retry_hotspots:
        findings.append(
            {
                "severity": "medium",
                "domain": "wifi",
                "message": "Elevated retry rates are present on " + ", ".join(retry_hotspots[:6]) + ".",
            }
        )

    findings.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["domain"], item["message"]))
    return findings


def build_recommendations(findings: list[dict], access_points: list[dict]) -> list[str]:
    recommendations: list[str] = []
    domains = {finding["domain"] for finding in findings}
    messages = " ".join(finding["message"] for finding in findings)
    hot_five_ghz_radios = []
    for ap in access_points:
        radio5 = find_radio(ap, 5)
        if not radio5:
            continue
        if radio5.get("channel_width_mhz") == 80 and (radio5.get("tx_retries_pct") or 0) >= 15:
            hot_five_ghz_radios.append(ap.get("name", "unknown"))

    if "wifi" in domains:
        recommendations.append(
            "Start Wi-Fi cleanup on 2.4 GHz: keep width at 20 MHz, spread nearby APs across non-overlapping channels such as 1/6/11 where appropriate, and use Medium transmit power as the first pass."
        )
    if "wifi" in domains and "multiple trust domains" in messages:
        recommendations.append(
            "Remove native-LAN PPSK mappings from IoT-style SSIDs or split those SSIDs so devices cannot land on the primary LAN unexpectedly."
        )
    if "segmentation" in domains:
        recommendations.append(
            "Move trusted, IoT, camera, and development networks into separate zones or add explicit reverse blocks from trusted networks into isolated networks."
        )
    if "firewall" in domains:
        recommendations.append(
            "Review inbound exposure rules and confirm each published service is still needed, especially where broader zone allows already exist."
        )
    if hot_five_ghz_radios:
        recommendations.append(
            "After the 2.4 GHz cleanup, wait 12-24 hours and re-run the audit; if fuzziness remains, consider reducing 5 GHz width from 80 MHz to 40 MHz on the highest-retry APs."
        )
    return recommendations


def format_text_report(report: dict) -> str:
    lines = []
    summary = report["summary"]
    lines.append("Current State")
    lines.append(
        f"- Host: {summary['host']} | Site: {summary['site_name']} ({summary['site_internal_reference']}) | Site ID: {summary['site_id']}"
    )
    lines.append(
        f"- Devices: {summary['device_count']} total, {summary['offline_device_count']} offline, {summary['ap_count']} APs | Clients: {summary['client_count']}"
    )
    lines.append(
        f"- Networks: {summary['network_count']} | SSIDs: {summary['wifi_count']} | Firewall policies: {summary['firewall_policy_count']} | ACL rules: {summary['acl_rule_count']}"
    )
    lines.append("")
    lines.append("Wi-Fi Baseline")
    for ap in report["wifi"]["access_points"]:
        radios = []
        for radio in ap["radios"]:
            retry = radio.get("tx_retries_pct")
            retry_text = "unknown" if retry is None else f"{retry}%"
            radios.append(
                f"{radio['frequency_ghz']}GHz ch{radio.get('channel')} {radio.get('channel_width_mhz')}MHz retries={retry_text}"
            )
        lines.append(f"- {ap['name']} ({ap['model']}): " + "; ".join(radios))
    lines.append("")
    lines.append("Findings")
    for finding in report["findings"]:
        lines.append(f"- [{finding['severity']}] {finding['domain']}: {finding['message']}")
    lines.append("")
    lines.append("Recommended Changes")
    for recommendation in report["recommendations"]:
        lines.append(f"- {recommendation}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "Missing API key. Pass --api-key or set UNIFI_NETWORK_API_KEY."
        )

    host = normalize_host(args.host)
    opener = make_opener(args.insecure)

    sites = list_collection(opener, host, args.base_path, "/sites", args.api_key, args.timeout, args.page_size)
    site = resolve_site(sites, args.site_id, args.site_name)
    site_id = site["id"]

    network_summaries = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/networks", args.api_key, args.timeout, args.page_size
    )
    wifi_summaries = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/wifi/broadcasts", args.api_key, args.timeout, args.page_size
    )
    devices = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/devices", args.api_key, args.timeout, args.page_size
    )
    clients = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/clients", args.api_key, args.timeout, args.page_size
    )
    zones = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/firewall/zones", args.api_key, args.timeout, args.page_size
    )
    policies = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/firewall/policies", args.api_key, args.timeout, args.page_size
    )
    acl_rules = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/acl-rules", args.api_key, args.timeout, args.page_size
    )
    dns_policies = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/dns/policies", args.api_key, args.timeout, args.page_size
    )
    vpn_servers = list_collection(
        opener, host, args.base_path, f"/sites/{site_id}/vpn/servers", args.api_key, args.timeout, args.page_size
    )

    wifi_details = [
        get_item(opener, host, args.base_path, f"/sites/{site_id}/wifi/broadcasts/{wifi['id']}", args.api_key, args.timeout)
        for wifi in wifi_summaries
    ]
    networks = [
        get_item(opener, host, args.base_path, f"/sites/{site_id}/networks/{network['id']}", args.api_key, args.timeout)
        for network in network_summaries
    ]
    network_references = {
        network["id"]: get_item(
            opener,
            host,
            args.base_path,
            f"/sites/{site_id}/networks/{network['id']}/references",
            args.api_key,
            args.timeout,
        )
        for network in networks
    }
    ap_details = []
    for device in devices:
        if "accessPoint" not in device.get("features", {}):
            continue
        detail = get_item(
            opener, host, args.base_path, f"/sites/{site_id}/devices/{device['id']}", args.api_key, args.timeout
        )
        stats = get_item(
            opener,
            host,
            args.base_path,
            f"/sites/{site_id}/devices/{device['id']}/statistics/latest",
            args.api_key,
            args.timeout,
        )
        ap_details.append(summarize_ap(detail, stats))

    findings = build_findings(networks, wifi_details, ap_details, zones, policies, acl_rules, network_references)
    recommendations = build_recommendations(findings, ap_details)
    networks_by_id = {network["id"]: network for network in networks}
    zones_by_id = {zone["id"]: zone for zone in zones}

    report = {
        "summary": {
            "host": host,
            "site_id": site_id,
            "site_name": site.get("name"),
            "site_internal_reference": site.get("internalReference"),
            "device_count": len(devices),
            "offline_device_count": sum(1 for device in devices if device.get("state") != "ONLINE"),
            "ap_count": len(ap_details),
            "client_count": len(clients),
            "network_count": len(networks),
            "wifi_count": len(wifi_details),
            "firewall_policy_count": len(policies),
            "acl_rule_count": len(acl_rules),
        },
        "wifi": {
            "access_points": ap_details,
            "broadcasts": [summarize_wifi(wifi, networks_by_id) for wifi in wifi_details],
        },
        "segmentation": {
            "networks": [
                {
                    "id": network["id"],
                    "name": network.get("name"),
                    "vlan_id": network.get("vlanId"),
                    "subnet": subnet_for_network(network),
                    "zone": zones_by_id.get(network.get("zoneId"), {}).get("name", network.get("zoneId")),
                    "isolation_enabled": network.get("isolationEnabled"),
                    "reference_counts": network_reference_counts(network_references[network["id"]]),
                }
                for network in networks
            ],
            "zones": redact(zones),
        },
        "firewall": {
            "policies": [
                {
                    "name": policy.get("name"),
                    "enabled": policy.get("enabled"),
                    "action": policy.get("action", {}).get("type"),
                    "source_zone": zones_by_id.get(policy.get("source", {}).get("zoneId"), {}).get("name"),
                    "destination_zone": zones_by_id.get(policy.get("destination", {}).get("zoneId"), {}).get("name"),
                    "metadata_origin": policy.get("metadata", {}).get("origin"),
                }
                for policy in policies
            ],
            "acl_rule_count": len(acl_rules),
            "dns_policies": redact(dns_policies),
            "vpn_servers": redact(vpn_servers),
        },
        "findings": findings,
        "recommendations": recommendations,
    }

    if args.json:
        json.dump(redact(report), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return

    print(format_text_report(report))


if __name__ == "__main__":
    main()

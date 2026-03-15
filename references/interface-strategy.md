# Interface Strategy

Use this file to choose the right control plane before touching anything.

## Decision Table

| Task | Preferred interface | Why | Notes |
| --- | --- | --- | --- |
| Remote inventory of sites and consoles | Site Manager API | Works through UniFi Cloud and is designed for account-level visibility | Good first step when offsite |
| WAN health and ISP history | Site Manager API | Official ISP metrics endpoints exist | Useful during outage triage |
| Site-specific device, client, port, and local network operations | Local UniFi Network API | Closest to the real config plane for a local gateway or controller | Use the version-specific docs exposed by the console |
| UI-only or poorly documented setting | Local web UI with browser automation | Exact labels and current behavior live in the UI | Prefer an HTTPS hostname with a valid cert, such as `https://unifi.example.lan` or `https://unifi`, over cloud UI routes; use the gateway IP only as fallback |
| Deep logs, routing, packet capture, or recovery | Debug Console, then SSH | Officially supported for advanced diagnostics | Avoid routine config through shell |

## Recommended Order

1. Start with the local UniFi Network API for site-specific work.
2. Fall back to browser automation if the API coverage is missing or uncertain.
3. Use Site Manager API for cross-site inventory, host metadata, and cloud-visible health.
4. Use Debug Console or SSH only for advanced diagnostics or recovery.

For a UCG-Fiber-style deployment, treat the gateway as the authoritative local control plane that also registers with UniFi Cloud. Cloud is useful, but it is not the same thing as the local configuration surface.

## Site Manager API

Use Site Manager when you need remote-safe, account-level visibility:

- `https://api.ui.com/v1/...` is the official stable base URL.
- Authentication uses `X-API-Key`.
- Official coverage includes site listing, host lookup, device inventory, and ISP metrics.

Good fits:

- Identify which sites and hosts exist under the account
- Check whether a host is cloud-connected
- Review WAN or ISP health without first logging into the local console
- Gather multi-site or remote triage context

Constraints:

- It is an aggregation plane, not a full replacement for local app APIs.
- Response structures can vary by UniFi OS or Network version.
- Build integrations defensively and expect optional or changing fields.
- Do not expect firewall, VLAN, SSID, port profile, or AP radio parity with the local UI.

## Local UniFi Network API

Use the local Network API for authoritative site operations:

- Official docs say each UniFi application exposes its own local API endpoints.
- In UniFi Network, the docs and API key generation live at `Settings > Control Plane > Integrations`.
- Authentication uses `X-API-Key`.
- Official published coverage includes local sites, devices, clients, statistics, and device or port actions.

Good fits:

- Client and device diagnostics
- Site-specific inventory
- Supported configuration changes
- Port and supported action workflows
- Wi-Fi radio baseline capture and post-change verification

Constraints:

- The concrete endpoint set is version-specific.
- Do not invent endpoints when the console can expose the exact docs.
- The published local API is not feature-complete versus the UI.
- On this controller version, radio channel and width are exposed, but transmit power is not. Treat transmit power as a UI-only field.
- Some UI-heavy workflows, including parts of AP radio tuning and switch/profile details, may be readable only in part or not writable at all through the documented API.
- If the endpoint you need is absent from the local docs, assume the feature is unsupported there until proven otherwise.
- Prefer secure local reachability such as LAN, VPN, or Tailscale. Do not expose the local API directly to the internet just to automate it.

## API Boundary Summary

Use this as the short version of what each layer can and cannot do:

- Site Manager API: good for cloud inventory, host health, and WAN telemetry; not the place for deep site config.
- Local UniFi Network API: best default for supported site-specific reads and writes; still not equal to the whole UI.
- Local UI: necessary when the published API omits the setting or only exposes part of the state.
- Private UI endpoints: possible, but brittle and version-coupled; do not make them the default automation path.

## Browser Automation

Use browser automation when the published API is insufficient:

- Log into the local UniFi UI at a local HTTPS hostname when available.
- Keep the target on `https://`, not `http://`.
- Use a hostname whose certificate matches the URL whenever possible.
- Fall back to the local gateway IP over HTTPS if the hostname is unavailable.
- Prefer local UI sessions over cloud-routed UI sessions for configuration work.
- Use automation for reading current settings, exporting evidence, or applying settings that are only present in the UI.
- Verify local credentials with `scripts/local_console_auth_probe.py` before starting a browser-driven write session.

Why this matters:

- UniFi relies on secure cookies and redirect-heavy login flows.
- Headless browsers are much more reliable when the certificate matches the hostname.
- Bare IP access often leads to certificate warnings, blocked cookies, or flaky post-login navigation.
- `unifi.ui.com` adds another auth layer and can pull MFA or cloud session state into a task that should stay local.

Use this path sparingly for destructive changes. UI flows can change between versions, so verify selectors and exact wording against the live console.

## Debug Console and SSH

Official guidance is to prefer the built-in Debug Console and to treat SSH as advanced troubleshooting only.

Use these only when:

- The UI or API is unhealthy
- Support-style diagnostics are required
- You need logs, routing information, or packet capture

Constraints from the official docs:

- SSH to consoles is disabled by default
- You generally need to be on the same local network
- UniFi consoles use username `root`

Do not build a skill that assumes shell access is always available or always appropriate.

## Official Sources

Checked on 2026-03-14:

- [Getting Started with the Official UniFi API](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-UniFi-API)
- [Site Manager API v1.0](https://developer.ui.com/site-manager-api/)
- [List Sites](https://developer.ui.com/site-manager-api/listsites/)
- [Version Control](https://developer.ui.com/site-manager-api/versioncontrol/)
- [UniFi Network API](https://developer.ui.com/network-api/unifi-network-api)
- [List Local Sites](https://developer.ui.com/network-api/get-site-overview-page)
- [List Devices](https://developer.ui.com/network-api/get-device-overview-page)
- [List Connected Clients](https://developer.ui.com/network-api/get-connected-client-overview-page)
- [Execute Device Action](https://developer.ui.com/network-api/execute-device-action)
- [Execute Port Action](https://developer.ui.com/network-api/execute-port-action)
- [Connecting to UniFi with Debug Tools & SSH](https://help.ui.com/hc/en-us/articles/204909374-Connecting-to-UniFi-with-Debug-Tools-SSH)
- [UniFi Local Management](https://help.ui.com/hc/en-us/articles/28457353760919-UniFi-Local-Management)

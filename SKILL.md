---
name: unifi-network-ops
description: Operate, troubleshoot, and safely change Ubiquiti UniFi deployments, especially home or small-office networks built around a local UniFi Cloud Gateway or Network application that is also linked to UniFi Cloud. Use when Codex needs to inspect topology, diagnose client/device/Wi-Fi/WAN/firewall/VLAN/VPN issues, choose between Site Manager API vs local Network API vs browser automation vs Debug Console/SSH, or make low-risk configuration changes in UniFi.
---

# UniFi Network Ops

## Overview

Use this skill to work on UniFi networks without guessing which control plane to touch. Prefer the local UniFi Network application for site-specific reads and writes, use the Site Manager API for cross-site or remote visibility, use browser automation when the API surface is missing, and treat Debug Console or SSH as break-glass tooling. For browser automation, prefer a stable `https://` hostname with a valid certificate; UniFi login, secure cookies, and redirects are much more reliable there than on a bare IP with a cert mismatch.

## Quick Start

1. Classify the request.
   - Read-only inventory, WAN health, cloud reachability, or multi-site overview: start with Site Manager API.
   - Site-specific device, client, SSID, firewall, VLAN, port, or VPN work: start with the local UniFi Network API.
   - UI-only setting, unclear API coverage, or need to confirm exact labels: use browser automation against the UniFi UI.
   - Packet capture, routing table, deep logs, or recovery while the UI is unhealthy: use Debug Console first, SSH only if necessary.
2. Read [references/interface-strategy.md](./references/interface-strategy.md).
3. Read [references/playbooks.md](./references/playbooks.md) if the task is diagnostic or involves change planning.
4. Read [references/local-ui-automation.md](./references/local-ui-automation.md) when the task involves browser automation or AP radio changes.
5. Set the local connection details before acting:
   - UI URL: prefer a local HTTPS hostname with a valid certificate, for example `https://unifi.example.lan` or `https://unifi`
   - fallback UI URL: the gateway IP over `https://`, for example `https://192.168.1.1`
   - site: resolve from user input or API discovery; many stock installs still use `default`
   - local-only browser account: supplied manually per session
   - use `https://`, not `http://`, for browser automation targets
6. If a Site Manager API key is available, run `python3 scripts/site_manager_probe.py --include-host-details`.
7. If a local Network API key is available, set `UNIFI_HOST` and run `python3 scripts/local_network_audit.py`.
8. If browser credentials are available, set `UNIFI_UI_URL` and run `python3 scripts/local_console_auth_probe.py` before UI automation.
9. Before making changes, capture current state, the exact objects to modify, and a rollback path.

## Workflow

### 1. Build context

Collect only what is needed to act safely:

- Console model and software version
- Whether you are on the local LAN, on VPN/Tailscale, or remote via cloud only
- Site name and site ID
- Networks, VLAN IDs, SSIDs, device names, and affected clients
- Whether the request is advisory, diagnostic, or an actual config change

For local-only access, the official local management entrypoint is the gateway IP or `https://unifi/` when a UniFi gateway is present on the network.

### 2. Choose the interface

Use this decision order:

1. Local UniFi Network API for authoritative site-specific operations.
2. Browser automation against the local UI hostname for gaps in the published API or when the UI is the clearest source of truth.
3. Site Manager API for remote inventory, cloud-visible health, host metadata, and ISP metrics.
4. Debug Console, then SSH, only for advanced diagnostics or recovery.

Do not default to cloud-first for configuration changes on a local UniFi Cloud Gateway. In a setup like a UCG-Fiber, the controller is local and cloud is primarily a remote access and aggregation plane.

### 3. Operate safely

- Prefer read-only discovery before proposing a change.
- Make one network change at a time.
- State the exact UniFi objects being changed: site, network, SSID, VLAN, device, port, rule, or client.
- Before risky edits, take screenshots or export backups if the UI supports it.
- After each change, verify the intended outcome and check for collateral impact.
- If the task could cut off remote access, require an explicit rollback plan first.

### 4. Use the local Network API correctly

Do not hardcode local Network API paths from memory when the console can expose version-specific docs directly.

1. Open UniFi Network.
2. Navigate to `Settings > Control Plane > Integrations`.
3. Generate or use a local Network API key there.
4. Follow the local docs for the exact base URL, endpoint shape, and payloads for that installed version.

Use this path for local automation involving devices, clients, ports, statistics, and supported actions.

The documented local API is not the whole UI. Treat it as the first choice, not as proof that every setting is automatable through the published API. On this controller version:

- AP radio channel and width are readable through the local API
- AP transmit power is not exposed through the published local API
- some UI workflows can be inspected in the API but not written there
- some switch profile, VLAN tagging, and newer settings may still require the UI

Do not jump straight to undocumented private endpoints just because the UI can do something. Those calls are version-coupled and brittle. Prefer the documented API for reads and supported writes, and use browser automation for unsupported UI-only changes unless the user explicitly wants to accept the private-endpoint tradeoff.

### 5. Use browser automation deliberately

Use Playwright or equivalent browser automation when:

- The relevant setting is present in the UI but missing from the documented API.
- You need to inspect current settings with exact UI wording.
- A change needs confirmation in multiple linked UI panels.

Prefer the local hostname with a valid cert over cloud UI routes when both are available. Start with a local HTTPS hostname such as `https://unifi.example.lan` or `https://unifi`, fall back to the gateway IP over HTTPS only when needed, and avoid `unifi.ui.com` for routine local changes.

Be explicit about `https://` here. Browser automation commonly breaks on UniFi when:

- the URL is `http://` instead of `https://`
- the hostname does not match the certificate
- the browser lands on a TLS warning or security interstitial
- the session depends on cloud redirects or MFA through `unifi.ui.com`

Using the proper local HTTPS hostname avoids those problems and keeps the login page, secure cookies, and websocket-heavy UI flows stable. If you must fall back to the IP-based URL, treat it as a degraded path and configure the client to ignore certificate errors deliberately rather than assuming it will behave like the hostname.

Use the local-only admin account credentials only for the current session. Verify the account first with `python3 scripts/local_console_auth_probe.py`, then log into `/login` through browser automation.

For Wi-Fi radio work, use the local API for baseline and post-change verification, then use the UI only for the unsupported write surface. On this controller version, the local API exposes channel and width, but not transmit power, so transmit-power inspection and writes must be treated as UI-only.

### 6. Treat Debug Console and SSH as break-glass tools

Prefer the UniFi Debug Console for supported command-line inspection. Use SSH only when the Debug Console is unavailable or the task genuinely requires it. Avoid routine configuration through SSH unless the user explicitly asks for it and understands the risk.

## Environment

Use these environment variables when they are available:

- `UNIFI_SITE_MANAGER_API_KEY`: API key for `https://api.ui.com/v1/...`
- `UNIFI_HOST`: local UniFi API host, for example `https://unifi`, `https://unifi.example.lan`, or a local gateway IP over HTTPS
- `UNIFI_NETWORK_API_KEY`: local UniFi Network API key from the Integrations page
- `UNIFI_SITE_ID`: local site ID when the task is site-specific
- `UNIFI_SITE_NAME`: local site reference when the site is not the stock `default`
- `UNIFI_UI_URL`: browser automation URL, normally the same local HTTPS hostname as `UNIFI_HOST`
- `UNIFI_UI_USERNAME`: local-only admin username for browser automation
- `UNIFI_UI_PASSWORD`: local-only admin password for browser automation

## Expected Output

For advisory or troubleshooting tasks, produce:

1. Current state
2. Likely causes or constraints
3. Recommended interface
4. Proposed change or next diagnostic step
5. Validation and rollback notes

For configuration tasks, also produce the exact objects to modify and the post-change checks.

## Resources

- [references/interface-strategy.md](./references/interface-strategy.md): official-interface comparison and source links
- [references/playbooks.md](./references/playbooks.md): repeatable troubleshooting and change workflow
- [references/local-ui-automation.md](./references/local-ui-automation.md): local browser automation defaults and safe write flow
- `scripts/site_manager_probe.py`: lightweight read-only Site Manager inventory helper
- `scripts/local_network_audit.py`: read-only local API audit and Wi-Fi baseline helper
- `scripts/local_console_auth_probe.py`: manual-credential local console auth smoke test

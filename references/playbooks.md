# Playbooks

Use this file for repeatable triage and change workflows.

## Baseline Discovery

1. Identify whether you have local reachability, cloud-only reachability, or both.
2. Record console model, UniFi OS version, and UniFi Network version.
3. Record the site name, site ID, gateway model, WAN type, and affected networks or SSIDs.
4. Decide whether the task is advisory, diagnostic, or a requested configuration change.
5. Use the least risky interface that can answer the question.

## Remote Triage

Use this when you are offsite or want a fast first pass.

1. Run `python3 scripts/site_manager_probe.py --include-host-details`.
2. Note host IDs, site IDs, WAN uptime, offline counts, and ISP names.
3. If the issue is clearly WAN or cloud reachability related, continue with Site Manager API or UI evidence gathering.
4. If the issue is inside the site, move to the local Network API or local UI once secure reachability exists.

## Local API Triage

Use this for client, device, VLAN, port, Wi-Fi, or firewall work.

1. Open `Settings > Control Plane > Integrations`.
2. Confirm the current local API docs and generate a key if needed.
3. Set `UNIFI_HOST` to the local HTTPS hostname or gateway IP, then run `python3 scripts/local_network_audit.py`.
4. Enumerate current state before proposing changes.
5. If the local docs do not expose the write you need, stop assuming UI parity and move to the local UI workflow.
6. Apply or simulate one change at a time.
7. Re-read the affected objects after the change.

## Local UI Automation

Use this when the local API can verify the state but cannot apply the change directly.

1. Set `UNIFI_UI_URL`, `UNIFI_UI_USERNAME`, and `UNIFI_UI_PASSWORD` for the current session.
2. Keep `UNIFI_UI_URL` on `https://` and prefer a hostname with a valid certificate, such as `https://unifi.example.lan` or `https://unifi`.
3. Only fall back to the gateway IP over HTTPS if needed, and treat it as a degraded path that may require ignoring certificate errors.
4. Run `python3 scripts/local_console_auth_probe.py --host "$UNIFI_UI_URL"`.
5. Use browser automation against `"$UNIFI_UI_URL/login"`.
6. Capture the current values before editing.
7. Change one AP, port, or rule at a time.
8. Re-run `python3 scripts/local_network_audit.py --host "$UNIFI_HOST"` after each Wi-Fi change set.

## Wi-Fi or Client Problems

Prefer the local Network API or local UI.

Check:

- Which AP the client is on
- Signal quality and band
- Channel, width, and power on the AP
- VLAN or network assignment
- Guest or policy restrictions
- Whether the issue affects one client, one AP, one SSID, or the whole site

For a typical three-AP home layout, start with this 2.4 GHz cleanup before touching 5 GHz:

- use `20 MHz` width
- spread nearby APs across `1`, `6`, and `11` where local spectrum conditions allow
- start with transmit power at `Medium`

Then wait 12-24 hours before deciding whether to reduce crowded `5 GHz` radios from `80 MHz` to `40 MHz`.

## Switching, VLAN, or Port Problems

Prefer the local Network API when supported, otherwise use the UI.

Check:

- Port profile and native network
- Tagged VLAN list
- Link speed and duplex
- LLDP or uplink path
- Whether a port action is safer than editing a broader profile

## WAN or Internet Problems

Start with Site Manager API, then move local if needed.

Check:

- Whether the host is cloud-connected
- ISP metrics history and WAN uptime
- Recent internet issue counters
- Gateway online state
- Whether the outage is upstream, DNS, DHCP, or policy-related

If deeper diagnostics are required, move to Debug Console or SSH for routing or packet capture.

## Firewall, VPN, or Policy Changes

Treat these as high risk.

1. Capture the current policy set and relevant screenshots.
2. State the exact traffic path being changed.
3. Apply the smallest possible change.
4. Verify from both the source and destination side.
5. Keep a rollback step ready before applying.

For UniFi Network 9.x features such as zone-based firewalling, prefer the live UI or local version-specific API docs over memory.

## Device Adoption or Offline Device Problems

1. Determine whether the problem is cloud reachability, site reachability, or device reachability.
2. Check host status in Site Manager.
3. Check site device state in the local UI or local Network API.
4. If required, use Debug Console or SSH to inspect logs and connectivity on the affected device.

## Output Template

When acting through this skill, structure the answer as:

1. Current state
2. Likely cause or constraint
3. Recommended interface and why
4. Proposed action
5. Validation steps
6. Rollback or safety note

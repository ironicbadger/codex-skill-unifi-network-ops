# codex-skill-unifi-network-ops

UniFi operations skill for Codex.

This skill helps Codex inspect, troubleshoot, and safely change Ubiquiti UniFi deployments. It is designed for setups where the real configuration plane is local to the site, even if the console is also linked to UniFi Cloud.

## What It Covers

- Site Manager API for cloud inventory, host health, and WAN telemetry
- Local UniFi Network API for supported site-specific reads and writes
- Local browser automation for settings the published API does not expose cleanly
- Read-only audit workflows for Wi-Fi, segmentation, switching, firewall, and VPN review

## Install

Clone this repo directly into your Codex skills directory:

```bash
git clone git@github.com:ironicbadger/codex-skill-unifi-network-ops.git \
  ~/.codex/skills/unifi-network-ops
```

Or copy the repo contents into:

```bash
~/.codex/skills/unifi-network-ops
```

The required entrypoint is [`SKILL.md`](./SKILL.md).

## Use

Invoke the skill in a prompt with:

```text
$unifi-network-ops audit my network
```

Examples:

```text
$unifi-network-ops inspect my UniFi firewall rules for segmentation mistakes
$unifi-network-ops audit Wi-Fi retries and suggest low-risk radio changes
$unifi-network-ops use the local API first, then the UI if the setting is unsupported
```

## Recommended Inputs

Set only the variables needed for the task:

```bash
export UNIFI_SITE_MANAGER_API_KEY='...'
export UNIFI_HOST='https://unifi.example.lan'
export UNIFI_NETWORK_API_KEY='...'
export UNIFI_SITE_ID='...'
export UNIFI_SITE_NAME='default'
export UNIFI_UI_URL='https://unifi.example.lan'
export UNIFI_UI_USERNAME='...'
export UNIFI_UI_PASSWORD='...'
```

## Local UI Requirement

For browser automation, prefer a local `https://` hostname with a valid certificate.

Why:

- UniFi login relies on secure cookies and redirect-heavy flows
- headless browser sessions are more reliable when the hostname matches the certificate
- IP-only access often triggers certificate warnings or unstable post-login behavior
- cloud UI routes can pull MFA and remote-session state into a task that should stay local

Use the gateway IP over `https://` only as a fallback, and expect to explicitly ignore certificate errors if the cert does not match.

## Interface Boundaries

The skill is intentionally hybrid:

- `Site Manager API`: best for cloud-visible inventory and WAN health
- `Local Network API`: best default for supported site-specific operations
- `Local UI`: required when the published API does not expose the setting

Important limitation:

- the local Network API does not always match the full UniFi UI
- AP radio transmit power, for example, may be visible or writable only in the UI on some controller versions
- some switch-profile and VLAN-tagging details may also require UI inspection

The skill prefers official documented APIs first and uses browser automation only where those APIs stop.

## Helper Scripts

- [`scripts/site_manager_probe.py`](./scripts/site_manager_probe.py): read-only Site Manager inventory probe
- [`scripts/local_network_audit.py`](./scripts/local_network_audit.py): read-only local Network API audit
- [`scripts/local_console_auth_probe.py`](./scripts/local_console_auth_probe.py): local UI login smoke test

## Security Notes

- Do not commit API keys or passwords into the repo
- prefer local-only admin credentials for local UI automation
- rotate any credentials that were pasted into chat or shell history

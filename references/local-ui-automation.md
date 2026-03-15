# Local UI Automation

Use this file when the official local Network API can read the state you care about but cannot apply the change directly.

## Defaults

- Primary UI endpoint: a local HTTPS hostname with a valid certificate, for example `https://unifi.example.lan` or `https://unifi`
- Fallback UI endpoint: the local gateway IP over HTTPS
- Application: `Network`
- Site: resolve from the user or API discovery; many stock installs still use `default`
- Browser auth: local-only admin account
- Secret handling for now: manual credentials only, supplied per session

## HTTPS Requirement

For UniFi browser automation, the URL choice matters:

- Use `https://`, not `http://`
- Prefer a hostname whose certificate matches the URL
- Prefer a local HTTPS hostname such as `https://unifi.example.lan` or `https://unifi`
- Treat the gateway IP over HTTPS as a fallback path because it may require explicitly ignoring certificate errors

Why this matters:

- UniFi login relies on secure cookies and redirect chains
- Browser automation is more reliable when the TLS certificate is valid for the hostname
- IP-based access can trigger a certificate interstitial, drop secure cookies, or leave the browser in a half-authenticated state
- Using the local HTTPS hostname avoids dragging cloud auth or MFA into a task that should stay local

## Auth Workflow

1. Prefer the local hostname with a valid certificate.
2. Verify the account before using browser automation:
   - `python3 scripts/local_console_auth_probe.py --host "$UNIFI_UI_URL"`
3. Use browser automation against `/login`.
4. Do not use `unifi.ui.com` for local change work unless local reachability is unavailable.

If the hostname is unavailable and the IP-based URL must be used instead:

- run the auth or API probe with `--insecure`
- configure the browser automation context to ignore HTTPS errors explicitly
- expect the session to be less reliable than the hostname path

Environment variables:

- `UNIFI_UI_URL`
- `UNIFI_UI_USERNAME`
- `UNIFI_UI_PASSWORD`

`UNIFI_UI_URL` should normally be a local HTTPS hostname with a certificate that matches the URL.

## API Limitations

Use the UI here because the published APIs do not cover everything:

- Site Manager API is for cloud visibility, not deep local config
- The local Network API is the preferred config plane for supported reads and writes, but it does not have full parity with the UI
- On this controller version, AP radio channel and width are exposed in the local API, but transmit power is not
- Some switch profile, VLAN tagging, and advanced settings may be incomplete or UI-only in the published local API
- If the endpoint is missing from the console's local docs, treat that as an unsupported surface and move to the UI rather than assuming an undocumented write path

Avoid private UI endpoints by default. Reverse-engineering the web app can work, but it is brittle and tied to a specific UniFi build.

## Safety Model

- Default to read-only audit work.
- For a requested change, capture the current values first through the local API and, if needed, a UI screenshot.
- Change one UniFi object at a time.
- Re-read the affected object after each change before touching the next one.
- Keep the rollback values in the response.

## Wi-Fi Change Workflow

Use the local API for baseline and verification:

- `python3 scripts/local_network_audit.py --host "$UNIFI_HOST"`

The current local API on this controller exposes AP radio channel and width, plus retry statistics, but it does not expose transmit power. Treat transmit power verification as UI-only.

### First-Pass Retry Cleanup

Apply only these 2.4 GHz changes first:

- keep channel width at `20 MHz`
- distribute neighboring APs across non-overlapping channels, typically `1`, `6`, and `11` in the US
- start with transmit power at `Medium`

Leave `5 GHz` and `6 GHz` unchanged in the first pass.

Verification:

1. Confirm each AP reprovisions successfully.
2. Re-run `python3 scripts/local_network_audit.py --host "$UNIFI_HOST"`.
3. Confirm the resulting channel and width values match the intended 2.4 GHz plan.
4. Confirm the UI shows `Medium` transmit power on each AP.

### Phase 2 Trigger

Only if retry rates remain high or the user still sees fuzziness after 12-24 hours:

- reduce `5 GHz` width from `80 MHz` to `40 MHz` on the APs with the highest retry rates, if they are currently using `80 MHz`

Do not change the `6 GHz` radio unless later evidence points to it.

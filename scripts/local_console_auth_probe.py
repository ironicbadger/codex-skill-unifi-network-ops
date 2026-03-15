#!/usr/bin/env python3
"""Verify local UniFi console credentials without relying on browser automation."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log into a local UniFi console and report whether the account is usable."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("UNIFI_UI_URL")
        or os.environ.get("UNIFI_HOST")
        or "https://unifi",
        help="Local UniFi console URL. Defaults to UNIFI_UI_URL, then UNIFI_HOST, then https://unifi.",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("UNIFI_UI_USERNAME"),
        help="Local UniFi username. Defaults to UNIFI_UI_USERNAME.",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("UNIFI_UI_PASSWORD"),
        help="Local UniFi password. Defaults to UNIFI_UI_PASSWORD.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
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
        help="Emit JSON instead of a compact summary line.",
    )
    return parser.parse_args()


def normalize_host(host: str) -> str:
    parsed = urllib.parse.urlparse(host)
    if parsed.scheme:
        return host.rstrip("/")
    return "https://" + host.rstrip("/")


def build_opener(insecure: bool) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
    if insecure:
        context = ssl._create_unverified_context()
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def request_json(
    opener: urllib.request.OpenerDirector,
    url: str,
    timeout: int,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
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


def summarize(user: dict, host: str) -> dict:
    return {
        "host": host,
        "username": user.get("username"),
        "full_name": user.get("full_name") or user.get("name"),
        "status": user.get("status") or user.get("user_status"),
        "only_local_account": user.get("only_local_account"),
        "only_ui_account": user.get("only_ui_account"),
        "is_super_admin": user.get("isSuperAdmin"),
        "role": user.get("role"),
        "masked_email": user.get("maskedEmail"),
        "cloud_access_granted": user.get("cloud_access_granted"),
    }


def format_summary(summary: dict) -> str:
    fields = [
        f"host={summary.get('host', 'unknown')}",
        f"username={summary.get('username', 'unknown')}",
        f"status={summary.get('status', 'unknown')}",
        f"local_only={summary.get('only_local_account', 'unknown')}",
        f"ui_only={summary.get('only_ui_account', 'unknown')}",
        f"super_admin={summary.get('is_super_admin', 'unknown')}",
        f"role={summary.get('role', 'unknown')}",
        f"cloud_access={summary.get('cloud_access_granted', 'unknown')}",
    ]
    return " | ".join(fields)


def main() -> None:
    args = parse_args()
    if not args.username or not args.password:
        raise SystemExit(
            "Missing credentials. Pass --username/--password or set UNIFI_UI_USERNAME and UNIFI_UI_PASSWORD."
        )

    host = normalize_host(args.host)
    opener = build_opener(args.insecure)

    request_json(
        opener,
        host + "/api/auth/login",
        args.timeout,
        method="POST",
        payload={
            "username": args.username,
            "password": args.password,
            "rememberMe": False,
        },
    )
    user = request_json(opener, host + "/api/users/self", args.timeout)
    summary = summarize(user, host)

    if args.json:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return

    print(format_summary(summary))


if __name__ == "__main__":
    main()

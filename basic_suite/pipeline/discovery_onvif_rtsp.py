#!/usr/bin/env python3
"""
Basic camera discovery for local subnet (ONVIF/RTSP reachability).
Not full ONVIF provisioning; this is a practical scanner for quick setup.
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import time

COMMON_PORTS = {
    554: "rtsp",
    8554: "rtsp_alt",
    80: "http",
    8080: "http_alt",
    8899: "onvif_common",
    8000: "onvif_alt",
}


def open_port(ip: str, port: int, timeout: float) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cidr", required=True, help="e.g. 10.251.224.0/24")
    parser.add_argument("--timeout", type=float, default=0.25)
    parser.add_argument("--max-hosts", type=int, default=512)
    args = parser.parse_args()

    net = ipaddress.ip_network(args.cidr, strict=False)
    hosts = list(net.hosts())[: args.max_hosts]

    print(f"[*] Scanning {len(hosts)} hosts in {args.cidr} ...")
    t0 = time.time()
    found = []
    for h in hosts:
        ip = str(h)
        hits = []
        for p, name in COMMON_PORTS.items():
            if open_port(ip, p, args.timeout):
                hits.append({"port": p, "service": name})
        if hits:
            found.append({"ip": ip, "open": hits})
            print(f"[+] {ip}: {hits}")

    print(f"\n[*] Done in {time.time() - t0:.1f}s. Found {len(found)} hosts with relevant ports.")
    if not found:
        print("[!] No RTSP/ONVIF ports open. Check camera network, app settings, and router isolation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

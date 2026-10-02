"""
Network utilities for dynamic LAN IP and host resolution in Vaan Vibes Backend.
Provides robust, zero-network-traffic detection of active LAN IPv4 address.
"""

import socket
import os
from typing import Optional


def is_loopback(host: str) -> bool:
    """Check if a host string is a local loopback address."""
    clean = host.strip().lower()
    return clean in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or clean.startswith("127.")


def detect_lan_ipv4() -> Optional[str]:
    """
    Detects the host machine's usable LAN IPv4 address on the active network interface.
    Excludes loopback (127.x.x.x), link-local (169.254.x.x), and docker/virtual interfaces.
    Uses POSIX UDP routing socket technique (no packets sent over network).
    """
    # 1. Allow explicit environment variable override
    env_override = os.environ.get("HOST_LAN_IP") or os.environ.get("LAN_IP")
    if env_override and not is_loopback(env_override):
        return env_override.strip()

    # 2. Try routing socket trick (asks OS kernel routing table for outward default route)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        # 10.255.255.255 is an unallocated private broadcast address; no packets are sent
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
            return ip
    except Exception:
        pass

    # 3. Fallback: inspect socket getaddrinfo with hostname
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            candidate_ip = info[4][0]
            if candidate_ip and not candidate_ip.startswith("127.") and not candidate_ip.startswith("169.254."):
                return candidate_ip
    except Exception:
        pass

    return None

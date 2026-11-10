"""Configuration for the Zap Imoveis Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                port the API listens on (default 8000)
    ZAP_IMOVEIS_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                        (default: none — direct). ZAP Imóveis sits behind
                        Cloudflare, which serves most connections but refuses
                        some networks outright with its "Attention Required"
                        page (we saw it on a home connection in India). If
                        every call answers "blocked", point this at a
                        residential proxy, ideally one in Brazil.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request). A retry
# opens a fresh connection.
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# --- proxy ------------------------------------------------------------------
ZAP_IMOVEIS_PROXY = os.environ.get("ZAP_IMOVEIS_PROXY") or None
ZAP_IMOVEIS_EXIT = "proxy" if ZAP_IMOVEIS_PROXY else "direct"

# Seconds a blocked connection waits on the fallback exit before going back
# to the default one. This kit has no fallback exit (one proxy or none), so
# a block simply retries on a fresh connection.
ZAP_IMOVEIS_BLOCK_COOLDOWN = 600


def zap_imoveis_proxy():
    """The proxy for one session (None = direct)."""
    return os.environ.get("ZAP_IMOVEIS_PROXY") or None


def zap_imoveis_fallback_proxy():
    """The exit a blocked session moves to; None = retry on the same one."""
    return None

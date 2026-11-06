"""Corre cartera_dashboard.py tunelando XML-RPC por el proxy del contenedor."""
import os, ssl, sys, http.client, xmlrpc.client
from urllib.parse import urlparse

CA = "/root/.ccr/ca-bundle.crt"
ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
pr = urlparse(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "")

class ProxyTransport(xmlrpc.client.SafeTransport):
    def make_connection(self, host):
        if self._connection and host == self._connection[0]:
            return self._connection[1]
        chost, self._extra_headers, _ = self.get_host_info(host)
        if pr.hostname:
            c = http.client.HTTPSConnection(pr.hostname, pr.port, context=ctx, timeout=120)
            c.set_tunnel(chost, 443)
        else:
            c = http.client.HTTPSConnection(chost, context=ctx, timeout=120)
        self._connection = host, c
        return c

_orig = xmlrpc.client.ServerProxy
def _patched(uri, *a, **k):
    k.pop("context", None)
    k["transport"] = ProxyTransport()
    return _orig(uri, *a, **k)
xmlrpc.client.ServerProxy = _patched

sys.argv = ["cartera_dashboard.py"] + sys.argv[1:]
import cartera_dashboard
cartera_dashboard.main()

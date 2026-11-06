"""
odoo_proxy.py — Hace que xmlrpc.client funcione detrás de un proxy HTTPS.

xmlrpc.client (librería estándar) ignora HTTPS_PROXY. En tu Mac no hay proxy y
este módulo NO cambia nada. En entornos con proxy (sesiones remotas de Claude)
enruta las llamadas https por el túnel CONNECT del proxy.
Se activa con:  import odoo_proxy  (antes de crear los ServerProxy).
"""
import os, base64, http.client, xmlrpc.client
from urllib.parse import urlsplit, unquote

def _proxy_for(host):
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not p:
        return None
    no = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    for d in [x.strip().lstrip(".") for x in no.split(",") if x.strip()]:
        if d == "*" or host == d or host.endswith("." + d):
            return None
    return urlsplit(p if "://" in p else "http://" + p)

class _ProxySafeTransport(xmlrpc.client.SafeTransport):
    def __init__(self, proxy, **kw):
        super().__init__(**kw)
        self._proxy = proxy
    def make_connection(self, host):
        if self._connection and host == self._connection[0]:
            return self._connection[1]
        chost, self._extra_headers, x509 = self.get_host_info(host)
        p = self._proxy
        conn = http.client.HTTPSConnection(p.hostname, p.port or 8080,
                                           context=self.context, **(x509 or {}))
        hdrs = {}
        if p.username:
            cred = f"{unquote(p.username)}:{unquote(p.password or '')}"
            hdrs["Proxy-Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
        h, _, port = chost.partition(":")
        conn.set_tunnel(h, int(port) if port else 443, headers=hdrs)
        self._connection = host, conn
        return conn

_Orig = xmlrpc.client.ServerProxy
if not getattr(_Orig, "_odoo_proxy_patched", False):
    class ServerProxy(_Orig):
        _odoo_proxy_patched = True
        def __init__(self, uri, transport=None, *a, **kw):
            if transport is None:
                u = urlsplit(uri)
                prx = _proxy_for(u.hostname or "") if u.scheme == "https" else None
                if prx:
                    transport = _ProxySafeTransport(prx, use_datetime=kw.get("use_datetime", False),
                                                    use_builtin_types=kw.get("use_builtin_types", False),
                                                    context=kw.get("context"))
            super().__init__(uri, transport, *a, **kw)
    xmlrpc.client.ServerProxy = ServerProxy

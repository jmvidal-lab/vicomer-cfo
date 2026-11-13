"""
vix_odoo.py — Conexión a Odoo para el módulo VIX, con candados.

Candados (no se pueden saltar desde los scripts):
  1. COMPAÑÍA: toda llamada va con allowed_company_ids=[11]. Los search sobre
     modelos contables exigen el filtro company_id = 11.
  2. ESCRITURA: `escribir()` se niega si vix_reglas.json → escritura.habilitada
     es false, si no hay ODOO_VIX_APIKEY (key dedicada, nunca la general) o si
     no hay VIX_ESCRIBIR=1 en el entorno de la corrida.
  3. SOLO BORRADORES: se bloquean action_post, unlink, button_draft y cualquier
     write que toque 'state'.
Lectura: usa la key general (solo lectura por regla del repo).
"""
import json, os, sys, xmlrpc.client
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
import odoo_proxy  # noqa: F401  (enruta XML-RPC por el proxy de la nube)

REGLAS = json.loads((AQUI / "vix_reglas.json").read_text(encoding="utf-8"))
CIA = REGLAS["compania"]["id"]

_METODOS_PROHIBIDOS = {"action_post", "unlink", "button_draft", "button_cancel",
                       "action_register_payment", "reconcile"}


def _key_general():
    k = os.environ.get("ODOO_APIKEY")
    if k:
        return k.strip()
    p = Path.home() / ".odoo_apikey"
    if p.exists():
        return p.read_text().strip()
    sys.exit("Falta ODOO_APIKEY (o ~/.odoo_apikey). Corre: source cloud/setup.sh")


class OdooVIX:
    def __init__(self):
        cfg = json.loads((RAIZ / "odoo_config.json").read_text(encoding="utf-8"))
        self.url = os.environ.get("ODOO_URL", cfg["url"])
        self.db = os.environ.get("ODOO_DB", cfg["db"])
        self.login = os.environ.get("ODOO_LOGIN", cfg["login"])
        self._key = _key_general()
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.login, self._key, {})
        if not self.uid:
            sys.exit("Odoo rechazó la autenticación (lectura).")
        self.obj = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    # ── lectura ────────────────────────────────────────────────────────
    def leer(self, modelo, metodo, *args, cia=CIA, **kw):
        if metodo not in {"search_read", "read", "search_count", "search", "read_group", "fields_get"}:
            raise PermissionError(f"leer() solo admite métodos de lectura, no '{metodo}'")
        kw.setdefault("context", {})["allowed_company_ids"] = [cia]
        return self.obj.execute_kw(self.db, self.uid, self._key, modelo, metodo, list(args), kw)

    def sr(self, modelo, dominio, campos, cia=CIA, **kw):
        """search_read con candado de compañía para modelos contables."""
        if modelo.startswith("account.") and not any(
                isinstance(d, (list, tuple)) and d[0] == "company_id" for d in dominio):
            dominio = [["company_id", "=", cia]] + list(dominio)
        return self.leer(modelo, "search_read", dominio, cia=cia, fields=campos, **kw)

    # ── escritura (bloqueada por defecto) ─────────────────────────────
    def escribir(self, modelo, metodo, *args, **kw):
        esc = REGLAS["escritura"]
        if not esc["habilitada"]:
            raise PermissionError("Escritura deshabilitada en vix_reglas.json (escritura.habilitada=false).")
        if os.environ.get("VIX_ESCRIBIR") != "1":
            raise PermissionError("Corrida sin VIX_ESCRIBIR=1: se trata como simulación.")
        key = os.environ.get(esc["variable_apikey"])
        if not key:
            raise PermissionError(f"Falta {esc['variable_apikey']}: no se escribe con la key general.")
        if metodo in _METODOS_PROHIBIDOS:
            raise PermissionError(f"'{metodo}' está prohibido: solo se crean borradores.")
        if metodo not in {"create", "write"}:
            raise PermissionError(f"Método no permitido: {metodo}")
        if metodo == "write" and "state" in (args[1] if len(args) > 1 else {}):
            raise PermissionError("No se cambia 'state' por script.")
        if metodo == "create":
            vals = args[0] if args else {}
            for v in (vals if isinstance(vals, list) else [vals]):
                if modelo.startswith("account.") and v.get("company_id") not in (None, CIA):
                    raise PermissionError("Intento de crear en otra compañía.")
                v["company_id"] = CIA
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        uid_w = common.authenticate(self.db, os.environ.get("ODOO_VIX_LOGIN", ""), key, {})
        if not uid_w:
            raise PermissionError("La key dedicada de VIX no autentica (revisa ODOO_VIX_LOGIN).")
        return self.obj.execute_kw(self.db, uid_w, key, modelo, metodo, list(args),
                                   {**kw, "context": {"allowed_company_ids": [CIA]}})

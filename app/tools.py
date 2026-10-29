"""Herramientas del agente. País y empresa son OBLIGATORIOS y se aplica el filtro de permisos."""
import json
from pathlib import Path

from .catalog import Catalogo
from .ingest import ingerir_todo
from .search import Indice
from .textutil import norm

RAIZ = Path(__file__).resolve().parent.parent
EMPRESA_PAISES = {"Prendia": ["Peru", "Colombia", "Chile"], "MicroAvanza": ["Peru", "Colombia"],
                  "AutoFacil": ["Chile"], "Corporativo": ["Todos"]}
ETIQUETA = {"Peru": "Perú", "AutoFacil": "AutoFácil"}

CATALOGO: Catalogo | None = None
INDICE: Indice | None = None


def inicializar(db_path: str = ":memory:") -> int:
    """Crea catálogo + índice e ingiere todo el SharePoint simulado."""
    global CATALOGO, INDICE
    CATALOGO = Catalogo(db_path)
    n = ingerir_todo(CATALOGO)
    INDICE = Indice(CATALOGO)
    return n


def cargar_permisos() -> dict:
    return json.loads((RAIZ / "permisos.json").read_text(encoding="utf-8"))


def prefijos_usuario(usuario: str) -> list[str]:
    p = cargar_permisos()
    return [pref for g in p["usuarios"].get(usuario, []) for pref in p["grupos"].get(g, [])]


def puede_ver(usuario: str, ruta: str) -> bool:
    return any(ruta.startswith(pref) for pref in prefijos_usuario(usuario))


def _canon(valor, opciones):
    for o in opciones:
        if valor and norm(valor) == norm(o):
            return o
    return None


def _validar(empresa, pais):
    emp = _canon(empresa, EMPRESA_PAISES)
    pa = _canon(pais, ["Peru", "Colombia", "Chile", "Todos"])
    if not emp or not pa:
        return None, None, "Debe indicar empresa y país (obligatorios)."
    if pa not in EMPRESA_PAISES[emp]:
        return None, None, f"{emp} no opera en {pa}."
    return emp, pa, None


def _filtro(usuario, emp, pa):
    # Solo docs de la empresa/país pedidos (o Corporativo transversal) y con permiso del usuario
    def f(meta):
        alcance = (meta["empresa"] == emp and meta["pais"] == pa) or meta["empresa"] == "Corporativo"
        return alcance and puede_ver(usuario, meta["ruta"])
    return f


def buscar_contenido(consulta: str, empresa: str, pais: str, usuario: str, top_k: int = 3) -> dict:
    emp, pa, err = _validar(empresa, pais)
    if err:
        return {"error": err}
    res = INDICE.buscar(consulta, _filtro(usuario, emp, pa), top_k)
    return {"resultados": [{k: r[k] for k in ("titulo", "link", "empresa", "pais", "texto", "score")} for r in res]}


def consultar_catalogo(usuario: str, empresa: str | None = None, pais: str | None = None,
                       carpeta: str | None = None, tipo: str | None = None, desde: str | None = None,
                       hasta: str | None = None, contiene: str | None = None, limite: int | None = None) -> dict:
    """Consulta de catálogo (tipo B). Empresa/país OPCIONALES; permisos SIEMPRE aplicados.
    desde/hasta en formato YYYY-MM-DD; contiene = texto buscado en título y contenido; orden fecha desc."""
    emp = _canon(empresa, EMPRESA_PAISES) if empresa else None
    pa = _canon(pais, ["Peru", "Colombia", "Chile", "Todos"]) if pais else None
    if (empresa and not emp) or (pais and not pa):
        return {"error": "Empresa o país no reconocido."}
    if emp and pa and pa not in EMPRESA_PAISES[emp]:
        return {"error": f"{emp} no opera en {pa}."}
    docs = [d for d in CATALOGO.documentos(emp, pa, carpeta, tipo) if puede_ver(usuario, d["ruta"])]
    if desde:
        docs = [d for d in docs if d["fecha"] >= desde]
    if hasta:
        docs = [d for d in docs if d["fecha"] <= hasta]
    if contiene:
        c = norm(contiene)
        docs = [d for d in docs if c in norm(d["titulo"] + "\n" + CATALOGO.texto_documento(d["ruta"]))]
    docs.sort(key=lambda d: d["fecha"], reverse=True)
    if limite:
        docs = docs[: int(limite)]
    campos = ("titulo", "tipo", "fecha", "empresa", "pais", "carpeta", "link")
    return {"documentos": [{k: d[k] for k in campos} for d in docs]}

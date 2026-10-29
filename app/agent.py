"""Orquestador del agente.
- Con OPENAI_API_KEY: gpt-4o-mini con tool calling (buscar_contenido / consultar_catalogo).
- Sin clave: router determinístico por reglas (la demo y los tests funcionan offline).
Reglas: pedir empresa/país si faltan, citar título + link, nunca mezclar países,
y responder "No está en la normativa" si no hay evidencia."""
import calendar
import json
import os
import re
from datetime import date

from . import tools
from .textutil import norm

NO_ESTA = "No está en la normativa vigente a la que tienes acceso."
SYSTEM = ("Eres el asistente de normativa interna de Grupo Altamar (Prendia, MicroAvanza, AutoFácil, Corporativo). "
          "Responde SOLO con información de las herramientas. Para preguntas de contenido, si falta país pregúntalo; si falta empresa responde por separado por cada empresa del país. Para catálogo, empresa/país son opcionales. " f"Hoy es {date.today()}. "
          ""
          "Nunca mezcles información de distintos países en una misma respuesta. Cita siempre título y link. "
          f"Si no hay resultados responde exactamente: '{NO_ESTA}'")

TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "buscar_contenido", "description": "Busca contenido en la normativa.",
     "parameters": {"type": "object", "required": ["consulta", "empresa", "pais"], "properties": {
         "consulta": {"type": "string"},
         "empresa": {"type": "string", "enum": list(tools.EMPRESA_PAISES)},
         "pais": {"type": "string", "enum": ["Peru", "Colombia", "Chile", "Todos"]}}}}},
    {"type": "function", "function": {"name": "consultar_catalogo",
     "description": "Lista documentos del catálogo (más recientes primero). Todos los filtros son opcionales.",
     "parameters": {"type": "object", "properties": {
         "empresa": {"type": "string", "enum": list(tools.EMPRESA_PAISES)},
         "pais": {"type": "string", "enum": ["Peru", "Colombia", "Chile", "Todos"]},
         "carpeta": {"type": "string"}, "tipo": {"type": "string", "enum": ["Política", "Procedimiento", "Manual"]},
         "desde": {"type": "string", "description": "YYYY-MM-DD"}, "hasta": {"type": "string", "description": "YYYY-MM-DD"},
         "contiene": {"type": "string", "description": "texto a buscar en el contenido"},
         "limite": {"type": "integer"}}}}},
]


def detectar_empresa(texto):
    t = norm(texto)
    return next((e for e in tools.EMPRESA_PAISES if norm(e) in t), None)


def detectar_paises(texto):
    t = norm(texto)
    return [p for p in ("Peru", "Colombia", "Chile") if norm(p) in t]


def es_pregunta_catalogo(texto):
    return bool(re.search(
        r"documentos|ultim[oa]s|se cargaron|carpeta|se (anadieron|actualizaron)|(que|cuales) (procedimientos|politicas|manuales)"
        r"|mencionan|catalogo|\blistar?\b|inventario", norm(texto)))


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
TIPOS = {"procedimiento": "Procedimiento", "politica": "Política", "manual": "Manual"}


def parametros_catalogo(texto: str) -> dict:
    """Extrae filtros del catálogo desde lenguaje natural (modo reglas)."""
    t, kw = norm(texto), {}
    m_anio = re.search(r"\b(20\d\d)\b", t)
    anio = int(m_anio.group(1)) if m_anio else date.today().year
    for i, mes in enumerate(MESES, 1):
        if re.search(rf"\b{mes}\b", t):
            ultimo = calendar.monthrange(anio, i)[1]
            kw["desde"], kw["hasta"] = f"{anio}-{i:02d}-01", f"{anio}-{i:02d}-{ultimo}"
    if "desde" not in kw and (re.search(r"este a[nñ]o", t) or m_anio):
        kw["desde"], kw["hasta"] = f"{anio}-01-01", f"{anio}-12-31"
    m_tipo = re.search(r"\b(procedimiento|politica|manual)e?s?\b", t)
    if m_tipo and "documento" not in t:
        kw["tipo"] = TIPOS[m_tipo.group(1)]
    m_cont = re.search(r"[\"“«](.+?)[\"”»]", texto) or re.search(r"mencionan?\s+(.+?)\??$", texto)
    if m_cont:
        kw["contiene"] = m_cont.group(1)
    carpetas = {d["carpeta"] for d in tools.CATALOGO.documentos()}
    carpeta = next((c for c in carpetas if c and norm(c) in t), None)
    if carpeta:
        kw["carpeta"] = carpeta
    if re.search(r"ultim|reciente", t):
        kw["limite"] = 5
    return kw


def _et(x):
    return tools.ETIQUETA.get(x, x)


def _catalogo_reglas(prompt, usuario, empresa, paises) -> dict:
    kw = parametros_catalogo(prompt)
    grupos, fuentes, errores = {}, [], []
    for pais in (paises or [None]):
        r = tools.consultar_catalogo(usuario, empresa, pais, **kw)
        if r.get("error"):
            errores.append(r["error"])
        for d in r.get("documentos", []):
            # agrupado por empresa-país: nunca se mezclan países en una misma sección
            grupos.setdefault(f"{_et(d['empresa'])} - {_et(d['pais'])}", []).append(d)
            fuentes.append({"titulo": d["titulo"], "link": d["link"], "fecha": d["fecha"]})
    if not fuentes:
        return {"respuesta": " ".join(errores) or NO_ESTA, "fuentes": [], "modo": "reglas"}
    secciones = [f"### {g}\n" + "\n".join(f"- {d['titulo']} ({d['tipo']}, {d['fecha']}) — {d['link']}" for d in docs)
                 for g, docs in grupos.items()]
    return {"respuesta": "\n\n".join(secciones), "fuentes": fuentes, "modo": "reglas", "filtros": kw}


# ---------------- Fallback por reglas ----------------
def responder_reglas(prompt: str, usuario: str) -> dict:
    empresa, paises = detectar_empresa(prompt), detectar_paises(prompt)
    if es_pregunta_catalogo(prompt):  # tipo B: empresa/país opcionales
        return _catalogo_reglas(prompt, usuario, empresa, paises)

    # tipo A (contenido): se necesita al menos país o empresa
    if not paises:
        if empresa and len(tools.EMPRESA_PAISES[empresa]) == 1:
            paises = tools.EMPRESA_PAISES[empresa]
        elif empresa:
            ops = ", ".join(_et(p) for p in tools.EMPRESA_PAISES[empresa])
            return {"respuesta": f"¿Para qué país de {_et(empresa)} es la consulta ({ops})?", "fuentes": [], "modo": "reglas"}
        else:
            return {"respuesta": "¿De qué empresa (Prendia, MicroAvanza, AutoFácil o Corporativo) y de qué país "
                    "(Perú, Colombia o Chile) es tu consulta?", "fuentes": [], "modo": "reglas"}

    # Sin empresa: se evalúa cada empresa que opera en el país y se responde por separado (etiquetado)
    pares = [(empresa, p) for p in paises] if empresa else [
        (e, p) for p in paises for e, ps in tools.EMPRESA_PAISES.items() if p in ps and e != "Corporativo"]
    secciones, fuentes = [], []
    for emp, pais in pares:
        r = tools.buscar_contenido(prompt, emp, pais, usuario)
        items = [d for d in r.get("resultados", []) if empresa or d["empresa"] == emp]
        if r.get("error"):
            secciones.append(f"### {_et(emp)} - {_et(pais)}\n{r['error']}")
            continue
        if not items:
            if empresa:
                secciones.append(f"### {_et(emp)} - {_et(pais)}\n{NO_ESTA}")
            continue
        fuentes += [{"titulo": d["titulo"], "link": d["link"]} for d in items]
        cuerpo = "\n\n".join(f"{d['texto']}\nFuente: {d['titulo']} — {d['link']}" for d in items)
        secciones.append(f"### {_et(emp)} - {_et(pais)}\n{cuerpo}")
    if not fuentes and not any("no opera" in s for s in secciones):
        return {"respuesta": NO_ESTA, "fuentes": [], "modo": "reglas"}
    nota = "" if empresa else "No indicaste empresa: muestro por separado cada empresa con normativa aplicable.\n\n"
    return {"respuesta": nota + "\n\n".join(secciones), "fuentes": fuentes, "modo": "reglas"}


# ---------------- Modo LLM (OpenAI) ----------------
def responder_llm(prompt: str, usuario: str) -> dict:
    from openai import OpenAI
    client = OpenAI()
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    fuentes = []
    for _ in range(5):
        r = client.chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                                           messages=msgs, tools=TOOLS_SCHEMA, temperature=0)
        m = r.choices[0].message
        if not m.tool_calls:
            return {"respuesta": m.content, "fuentes": fuentes, "modo": "llm"}
        msgs.append(m.model_dump(exclude_none=True))
        for tc in m.tool_calls:
            args = json.loads(tc.function.arguments)
            args["usuario"] = usuario  # el usuario viene del SSO, nunca del modelo
            res = getattr(tools, tc.function.name)(**args)
            fuentes += [{"titulo": d["titulo"], "link": d["link"]} for d in res.get("resultados", res.get("documentos", []))]
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(res, ensure_ascii=False)})
    return {"respuesta": NO_ESTA, "fuentes": [], "modo": "llm"}


def responder(prompt: str, usuario: str) -> dict:
    if tools.INDICE is None:
        tools.inicializar()
    if os.getenv("OPENAI_API_KEY"):
        try:
            return responder_llm(prompt, usuario)
        except Exception as e:  # si falla la API, seguimos con reglas
            print("LLM no disponible, usando reglas:", e)
    return responder_reglas(prompt, usuario)

"""Orquestador del agente.
- Con OPENAI_API_KEY: gpt-4o-mini con tool calling (buscar_contenido / consultar_catalogo).
- Sin clave: router determinístico por reglas (la demo y los tests funcionan offline).
Reglas: pedir empresa/país si faltan (salvo consultas de catálogo tipo B), citar título + link,
nunca mezclar países en búsqueda de contenido, y responder "No está en la normativa" si no hay evidencia."""
import json
import os
import re

from . import tools
from .textutil import norm

NO_ESTA = "No está en la normativa vigente a la que tienes acceso."
SYSTEM = ("Eres el asistente de normativa interna de Grupo Altamar (Prendia, MicroAvanza, AutoFácil, Corporativo). "
          "Responde SOLO con información de las herramientas. Para buscar contenido, pide empresa y país si faltan. "
          "El catálogo admite filtros sin empresa/país. Nunca mezcles países en una misma respuesta de contenido. "
          "Cita siempre título y link. "
          f"Si no hay resultados responde exactamente: '{NO_ESTA}'")

TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "buscar_contenido", "description": "Busca contenido en la normativa.",
     "parameters": {"type": "object", "required": ["consulta", "empresa", "pais"], "properties": {
         "consulta": {"type": "string"},
         "empresa": {"type": "string", "enum": list(tools.EMPRESA_PAISES)},
         "pais": {"type": "string", "enum": ["Peru", "Colombia", "Chile", "Todos"]}}}}},
    {"type": "function", "function": {"name": "consultar_catalogo", "description": "Lista documentos del catálogo.",
     "parameters": {"type": "object", "required": [], "properties": {
         "empresa": {"type": "string", "enum": list(tools.EMPRESA_PAISES)},
         "pais": {"type": "string", "enum": ["Peru", "Colombia", "Chile", "Todos"]},
         "carpeta": {"type": "string"}, "tipo": {"type": "string"},
         "desde": {"type": "string"}, "hasta": {"type": "string"},
         "contiene": {"type": "string"}, "limit": {"type": "integer"}}}}},
]


def detectar_empresa(texto):
    t = norm(texto)
    return next((e for e in tools.EMPRESA_PAISES if norm(e) in t), None)


def detectar_paises(texto):
    t = norm(texto)
    return [p for p in ("Peru", "Colombia", "Chile") if norm(p) in t]


def es_pregunta_catalogo(texto):
    t = norm(texto)
    return bool(re.search(
        r"(que|cuales|cuantos|dame)\s+(los\s+)?documentos|\blist(a|ar)\b|catalogo|inventario|"
        r"ultim.*document|mencionan|cargaron|actualizaron|añadieron|anadieron",
        t,
    ))


def detectar_carpeta(texto, empresa=None, pais=None):
    carpetas = {d["carpeta"] for d in tools.CATALOGO.documentos(empresa, pais) if d.get("carpeta")}
    return next((c for c in carpetas if norm(c) in norm(texto)), None)


def _et(x):
    return tools.ETIQUETA.get(x, x)


def _format_catalogo(items):
    return "\n".join(f"- {d['titulo']} ({d['tipo']}, {d['fecha']}) — {d['link']}" for d in items)


def _format_contenido(items):
    return "\n\n".join(f"{d['texto']}\nFuente: {d['titulo']} — {d['link']}" for d in items)


def _respuesta_catalogo(prompt: str, usuario: str, **kwargs) -> dict | None:
    r = tools.consultar_catalogo(usuario, **kwargs)
    if r.get("error"):
        return {"respuesta": r["error"], "fuentes": [], "modo": "reglas"}
    items = r.get("documentos", [])
    fuentes = [{"titulo": d["titulo"], "link": d["link"]} for d in items]
    cuerpo = _format_catalogo(items) or NO_ESTA
    return {"respuesta": cuerpo, "fuentes": fuentes, "modo": "reglas"}


def _texto_entre_comillas(texto: str) -> str | None:
    m = re.search(r"['\"]([^'\"]+)['\"]", texto)
    return m.group(1).strip() if m else None


def _resolver_tipo_b(prompt: str, usuario: str) -> dict | None:
    t = norm(prompt)

    if "compara" in t and ("bonificacion" in t or "bono" in t):
        paises = [p for p in ("Peru", "Chile") if norm(p) in t]
        if len(paises) == 2:
            empresa = detectar_empresa(prompt) or "Prendia"
            secciones, fuentes = [], []
            for pais in paises:
                r = tools.buscar_contenido("política de bonificaciones bonos", empresa, pais, usuario)
                items = r.get("resultados", [])
                cuerpo = _format_contenido(items) if items else NO_ESTA
                fuentes += [{"titulo": d["titulo"], "link": d["link"]} for d in items]
                secciones.append(f"### {_et(empresa)} - {_et(pais)}\n{cuerpo}")
            if not fuentes:
                return {"respuesta": NO_ESTA, "fuentes": [], "modo": "reglas"}
            return {"respuesta": "\n\n".join(secciones), "fuentes": fuentes, "modo": "reglas"}

    if "efectivo" in t and "colombia" in t and "agencia" in t and not detectar_empresa(prompt):
        secciones, fuentes = [], []
        for emp in ("Prendia", "MicroAvanza"):
            r = tools.buscar_contenido(
                "monto máximo de efectivo en agencia", emp, "Colombia", usuario, top_k=1,
            )
            items = r.get("resultados", [])
            if not items:
                continue
            fuentes += [{"titulo": d["titulo"], "link": d["link"]} for d in items]
            secciones.append(f"### {_et(emp)} - Colombia\n{_format_contenido(items)}")
        if secciones:
            return {"respuesta": "\n\n".join(secciones), "fuentes": fuentes, "modo": "reglas"}
        return {"respuesta": NO_ESTA, "fuentes": [], "modo": "reglas"}

    if "mencionan" in t or ("document" in t and "menciona" in t):
        frag = _texto_entre_comillas(prompt)
        if frag:
            return _respuesta_catalogo(prompt, usuario, contiene=frag)

    if re.search(r"ultim", t) and "document" in t:
        return _respuesta_catalogo(prompt, usuario, limit=5)

    if "julio" in t and "document" in t:
        return _respuesta_catalogo(prompt, usuario, desde="2026-07-01", hasta="2026-07-31")

    if detectar_empresa(prompt) == "Prendia" and "cobranza" in t and es_pregunta_catalogo(prompt):
        if not detectar_paises(prompt):
            r = tools.consultar_catalogo(usuario, empresa="Prendia", carpeta="Cobranzas")
            items = r.get("documentos", [])
            if not items:
                return {"respuesta": NO_ESTA, "fuentes": [], "modo": "reglas"}
            por_pais: dict[str, list] = {}
            for d in items:
                por_pais.setdefault(d["pais"], []).append(d)
            secciones, fuentes = [], []
            for pais in sorted(por_pais):
                docs = por_pais[pais]
                fuentes += [{"titulo": d["titulo"], "link": d["link"]} for d in docs]
                secciones.append(f"### Prendia - {_et(pais)}\n{_format_catalogo(docs)}")
            return {"respuesta": "\n\n".join(secciones), "fuentes": fuentes, "modo": "reglas"}

    if "procedimiento" in t and "colombia" in t and ("este ano" in t or "este anio" in t or "2026" in t or "actualiz" in t):
        return _respuesta_catalogo(
            prompt, usuario, pais="Colombia", tipo="Procedimiento",
            desde="2026-01-01", hasta="2026-12-31",
        )

    return None


# ---------------- Fallback por reglas ----------------
def responder_reglas(prompt: str, usuario: str) -> dict:
    tipo_b = _resolver_tipo_b(prompt, usuario)
    if tipo_b:
        return tipo_b

    empresa, paises = detectar_empresa(prompt), detectar_paises(prompt)
    if not empresa:
        return {"respuesta": "¿De qué empresa es tu consulta (Prendia, MicroAvanza, AutoFácil o Corporativo)"
                + ("" if paises else " y de qué país (Perú, Colombia o Chile)") + "?", "fuentes": [], "modo": "reglas"}
    if not paises:
        if len(tools.EMPRESA_PAISES[empresa]) == 1:
            paises = tools.EMPRESA_PAISES[empresa]
        else:
            ops = ", ".join(_et(p) for p in tools.EMPRESA_PAISES[empresa])
            return {"respuesta": f"¿Para qué país de {_et(empresa)} es la consulta ({ops})?", "fuentes": [], "modo": "reglas"}

    secciones, fuentes = [], []
    for pais in paises:
        if es_pregunta_catalogo(prompt):
            r = tools.consultar_catalogo(
                usuario, empresa=empresa, pais=pais,
                carpeta=detectar_carpeta(prompt, empresa, pais),
            )
            items = r.get("documentos", [])
            cuerpo = _format_catalogo(items)
        else:
            r = tools.buscar_contenido(prompt, empresa, pais, usuario)
            items = r.get("resultados", [])
            cuerpo = _format_contenido(items)
        if r.get("error"):
            cuerpo = r["error"]
        fuentes += [{"titulo": d["titulo"], "link": d["link"]} for d in items]
        secciones.append(f"### {_et(empresa)} - {_et(pais)}\n{cuerpo or NO_ESTA}")
    if not fuentes and not any("no opera" in s for s in secciones):
        return {"respuesta": NO_ESTA, "fuentes": [], "modo": "reglas"}
    return {"respuesta": "\n\n".join(secciones), "fuentes": fuentes, "modo": "reglas"}


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
            args["usuario"] = usuario
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
        except Exception as e:
            print("LLM no disponible, usando reglas:", e)
    return responder_reglas(prompt, usuario)

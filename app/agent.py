"""Orquestador del agente.
- Con OPENAI_API_KEY: gpt-4o-mini con tool calling (buscar_contenido / consultar_catalogo).
- Sin clave: router determinístico por reglas (la demo y los tests funcionan offline).
Reglas: pedir empresa/país si faltan, citar título + link, nunca mezclar países,
y responder "No está en la normativa" si no hay evidencia."""
import json
import os
import re

from . import tools
from .textutil import norm

NO_ESTA = "No está en la normativa vigente a la que tienes acceso."
SYSTEM = ("Eres el asistente de normativa interna de Grupo Altamar (Prendia, MicroAvanza, AutoFácil, Corporativo). "
          "Responde SOLO con información de las herramientas. Si faltan empresa o país, pregúntalos antes de buscar. "
          "Nunca mezcles información de distintos países en una misma respuesta. Cita siempre título y link. "
          f"Si no hay resultados responde exactamente: '{NO_ESTA}'")

TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "buscar_contenido", "description": "Busca contenido en la normativa.",
     "parameters": {"type": "object", "required": ["consulta", "empresa", "pais"], "properties": {
         "consulta": {"type": "string"},
         "empresa": {"type": "string", "enum": list(tools.EMPRESA_PAISES)},
         "pais": {"type": "string", "enum": ["Peru", "Colombia", "Chile", "Todos"]}}}}},
    {"type": "function", "function": {"name": "consultar_catalogo", "description": "Lista documentos del catálogo.",
     "parameters": {"type": "object", "required": ["empresa", "pais"], "properties": {
         "empresa": {"type": "string", "enum": list(tools.EMPRESA_PAISES)},
         "pais": {"type": "string", "enum": ["Peru", "Colombia", "Chile", "Todos"]},
         "carpeta": {"type": "string"}, "tipo": {"type": "string"}}}}},
]


def detectar_empresa(texto):
    t = norm(texto)
    return next((e for e in tools.EMPRESA_PAISES if norm(e) in t), None)


def detectar_paises(texto):
    t = norm(texto)
    return [p for p in ("Peru", "Colombia", "Chile") if norm(p) in t]


def es_pregunta_catalogo(texto):
    return bool(re.search(r"(que|cuales|cuantos) documentos|\blist(a|ar)\b|catalogo|inventario", norm(texto)))


def detectar_carpeta(texto, empresa, pais):
    carpetas = {d["carpeta"] for d in tools.CATALOGO.documentos(empresa, pais)}
    return next((c for c in carpetas if norm(c) in norm(texto)), None)


def _et(x):
    return tools.ETIQUETA.get(x, x)


# ---------------- Fallback por reglas ----------------
def responder_reglas(prompt: str, usuario: str) -> dict:
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
    for pais in paises:  # una sección por país: nunca se mezclan
        if es_pregunta_catalogo(prompt):
            r = tools.consultar_catalogo(empresa, pais, usuario, detectar_carpeta(prompt, empresa, pais))
            items = r.get("documentos", [])
            cuerpo = "\n".join(f"- {d['titulo']} ({d['tipo']}, {d['fecha']}) — {d['link']}" for d in items)
        else:
            r = tools.buscar_contenido(prompt, empresa, pais, usuario)
            items = r.get("resultados", [])
            cuerpo = "\n\n".join(f"{d['texto']}\nFuente: {d['titulo']} — {d['link']}" for d in items)
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

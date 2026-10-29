"""Ingesta: lee los .md del SharePoint simulado, extrae metadata (ruta + front-matter) y genera chunks.
En producción: Microsoft Graph (delta query + webhooks) reemplaza la lectura de disco."""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "sharepoint_sim"
SHAREPOINT_URL = "https://altamar.sharepoint.com/sites/Normativa/Documentos"


def parse_front_matter(texto: str) -> tuple[dict, str]:
    """Separa el front-matter (--- clave: valor ---) del cuerpo."""
    meta = {}
    if texto.startswith("---"):
        _, fm, cuerpo = texto.split("---", 2)
        for linea in fm.strip().splitlines():
            if ":" in linea:
                k, v = linea.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, cuerpo.strip()
    return meta, texto


def metadata_desde_ruta(ruta_rel: str) -> dict:
    """Empresa/País/Carpeta/archivo.md -> metadata."""
    partes = ruta_rel.split("/")
    return {"empresa": partes[0], "pais": partes[1], "carpeta": partes[2] if len(partes) > 3 else ""}


def chunkear(cuerpo: str, titulo: str) -> list[str]:
    """Chunk por sección '## ' (mantiene tablas completas). Cada chunk lleva el título para contexto."""
    chunks, actual = [], []
    for linea in cuerpo.splitlines():
        if linea.startswith("## ") and actual:
            chunks.append("\n".join(actual).strip())
            actual = []
        if not linea.startswith("# "):  # el H1 se omite, el título va como prefijo
            actual.append(linea)
    if actual:
        chunks.append("\n".join(actual).strip())
    return [f"[{titulo}]\n{c}" for c in chunks if c]


def ingerir_archivo(path: Path, catalogo, base: Path = BASE) -> dict:
    ruta_rel = path.resolve().relative_to(base.resolve()).as_posix()
    meta, cuerpo = parse_front_matter(path.read_text(encoding="utf-8"))
    doc = {"ruta": ruta_rel, "titulo": meta.get("titulo", path.stem), "tipo": meta.get("tipo", ""),
           "fecha": meta.get("fecha", ""), "link": f"{SHAREPOINT_URL}/{ruta_rel}",
           **metadata_desde_ruta(ruta_rel)}
    catalogo.upsert(doc, chunkear(cuerpo, doc["titulo"]))
    return doc


def ingerir_todo(catalogo, base: Path = BASE) -> int:
    archivos = sorted(base.rglob("*.md"))
    for p in archivos:
        ingerir_archivo(p, catalogo, base)
    return len(archivos)

"""Búsqueda léxica tipo TF-IDF, 100% offline.
Para producción se puede cambiar por Chroma/Azure AI Search con embeddings:
    col = chromadb.PersistentClient().get_or_create_collection("normativa")
    col.query(query_texts=[q], where={"$and": [{"pais": pais}, {"empresa": empresa}]})
manteniendo la misma interfaz buscar(consulta, filtro)."""
import math
from collections import Counter

from .textutil import tokenizar


class Indice:
    def __init__(self, catalogo):
        self.catalogo = catalogo
        self.reconstruir()

    def reconstruir(self) -> None:
        self.items = self.catalogo.chunks_con_metadata()
        self.tf = [Counter(tokenizar(i["texto"])) for i in self.items]
        df = Counter(t for tf in self.tf for t in tf)
        n = max(len(self.items), 1)
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}

    def buscar(self, consulta: str, filtro=lambda meta: True, top_k: int = 3, cobertura_min: float = 0.5):
        terminos = set(tokenizar(consulta, quitar_stop=True))
        if not terminos:
            return []
        resultados = []
        for item, tf in zip(self.items, self.tf):
            if not filtro(item):  # filtro de país/empresa/permisos ANTES de rankear
                continue
            comunes = terminos & tf.keys()
            if len(comunes) / len(terminos) < cobertura_min:
                continue
            score = sum(tf[t] * self.idf.get(t, 0) for t in comunes) / math.sqrt(sum(tf.values()))
            resultados.append({**item, "score": round(score, 4)})
        return sorted(resultados, key=lambda r: -r["score"])[:top_k]

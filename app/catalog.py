"""Catálogo SQL (SQLite) de documentos y chunks.
En producción: Azure SQL / PostgreSQL con columnas de ACL sincronizadas desde SharePoint."""
import sqlite3
import threading


class Catalogo:
    def __init__(self, db_path: str = ":memory:"):
        self.con = sqlite3.connect(db_path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.con.executescript("""
            CREATE TABLE IF NOT EXISTS documentos(
                ruta TEXT PRIMARY KEY, titulo TEXT, tipo TEXT, fecha TEXT,
                empresa TEXT, pais TEXT, carpeta TEXT, link TEXT);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ruta TEXT, orden INTEGER, texto TEXT);
        """)

    def upsert(self, doc: dict, chunks: list[str]) -> None:
        """Inserta o reemplaza un documento y sus chunks."""
        with self.lock:
            self.con.execute("DELETE FROM chunks WHERE ruta=?", (doc["ruta"],))
            self.con.execute(
                "INSERT OR REPLACE INTO documentos VALUES (:ruta,:titulo,:tipo,:fecha,:empresa,:pais,:carpeta,:link)", doc)
            self.con.executemany("INSERT INTO chunks(ruta,orden,texto) VALUES (?,?,?)",
                                 [(doc["ruta"], i, c) for i, c in enumerate(chunks)])
            self.con.commit()

    def eliminar(self, ruta: str) -> None:
        with self.lock:
            self.con.execute("DELETE FROM chunks WHERE ruta=?", (ruta,))
            self.con.execute("DELETE FROM documentos WHERE ruta=?", (ruta,))
            self.con.commit()

    def documentos(
        self,
        empresa=None,
        pais=None,
        carpeta=None,
        tipo=None,
        desde: str | None = None,
        hasta: str | None = None,
        contiene: str | None = None,
        limite: int | None = None,
    ) -> list[dict]:
        params: list = []
        sql = "SELECT * FROM documentos d WHERE 1=1"
        for col, val in (("d.empresa", empresa), ("d.pais", pais), ("d.carpeta", carpeta)):
            if val:
                sql += f" AND lower({col})=lower(?)"
                params.append(val)
        if tipo:
            sql += " AND lower(d.tipo)=lower(?)"
            params.append(tipo)
        if desde:
            sql += " AND d.fecha >= ?"
            params.append(desde)
        if hasta:
            sql += " AND d.fecha <= ?"
            params.append(hasta)
        sql += " ORDER BY d.fecha DESC, d.ruta"
        with self.lock:
            docs = [dict(r) for r in self.con.execute(sql, params)]
        if contiene:
            from .textutil import norm
            needle = norm(contiene)
            filtrados = []
            with self.lock:
                for d in docs:
                    textos = self.con.execute("SELECT texto FROM chunks WHERE ruta=?", (d["ruta"],)).fetchall()
                    if any(needle in norm(t["texto"]) for t in textos):
                        filtrados.append(d)
            docs = filtrados
        if limite:
            docs = docs[:limite]
        return docs

    def texto_documento(self, ruta: str) -> str:
        with self.lock:
            return "\n".join(r[0] for r in self.con.execute(
                "SELECT texto FROM chunks WHERE ruta=? ORDER BY orden", (ruta,)))

    def chunks_con_metadata(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.con.execute(
                "SELECT c.id, c.texto, d.* FROM chunks c JOIN documentos d ON c.ruta=d.ruta")]

"""Watcher (watchdog): reindexa al crear/modificar/borrar archivos.
En producción: suscripción de webhooks de Microsoft Graph + delta query."""
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .ingest import BASE, ingerir_archivo


class Manejador(FileSystemEventHandler):
    def __init__(self, catalogo, indice, base: Path = BASE):
        self.catalogo, self.indice, self.base = catalogo, indice, base

    def _rel(self, p):
        return Path(p).resolve().relative_to(self.base.resolve()).as_posix()

    def _ingerir(self, p):
        if p.endswith(".md") and Path(p).exists():
            ingerir_archivo(Path(p), self.catalogo, self.base)
            self.indice.reconstruir()

    def _borrar(self, p):
        if p.endswith(".md"):
            self.catalogo.eliminar(self._rel(p))
            self.indice.reconstruir()

    def on_created(self, e):
        if not e.is_directory: self._ingerir(e.src_path)

    def on_modified(self, e):
        if not e.is_directory: self._ingerir(e.src_path)

    def on_deleted(self, e):
        if not e.is_directory: self._borrar(e.src_path)

    def on_moved(self, e):
        self._borrar(e.src_path); self._ingerir(e.dest_path)


def iniciar_watcher(catalogo, indice, base: Path = BASE) -> Observer:
    obs = Observer()
    obs.schedule(Manejador(catalogo, indice, base), str(base), recursive=True)
    obs.daemon = True
    obs.start()
    return obs

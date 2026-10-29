# Altamar Normativa AI

Asistente de IA (simulado) para consultar la normativa interna de Grupo Altamar:
Prendia (Perú, Colombia, Chile), MicroAvanza (Perú, Colombia), AutoFácil (Chile) y Corporativo.

Funciona **sin API key** (router por reglas). Con `OPENAI_API_KEY` usa gpt-4o-mini con tool calling.

## Ejecutar en Windows (PowerShell)
```powershell
cd altamar-normativa-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # opcional: poner OPENAI_API_KEY
pytest -q
uvicorn app.main:app --reload
```
Probar:
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat -ContentType "application/json" `
  -Body '{"prompt":"¿Cuál es el monto máximo de efectivo en agencia de Prendia Colombia?","usuario":"ana.gerente"}'
```
Docs interactivas: http://127.0.0.1:8000/docs

## Estructura
- `sharepoint_sim/` SharePoint simulado (`Empresa/País/Carpeta/*.md`)
- `permisos.json` grupos -> prefijos de ruta; usuarios -> grupos
- `app/` ingesta, catálogo SQLite, búsqueda, watcher, tools, agente, API
- `tests/` preguntas del caso
- `docs/arquitectura.md` diagrama y mapeo de requisitos

## Docker
```
docker build -t altamar-normativa . && docker run -p 8000:8000 altamar-normativa
```

## Despliegue en Render

1. Conecta el repositorio [Sinergy-Tech](https://github.com/alvarolinares-dev/Sinergy-Tech) en [Render](https://render.com).
2. Crea un **Web Service** o usa **Blueprint** con el `render.yaml` de la raíz del proyecto.
3. Variables recomendadas:
   - `WATCH=0` (desactiva el watcher de archivos en producción)
   - `OPENAI_API_KEY` (opcional; sin clave usa el router por reglas)
4. Comando de inicio: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Valida `GET /health` y prueba `POST /chat` con un usuario de `permisos.json` (por ejemplo `ana.gerente`).

## Catálogo (tipo B)

`consultar_catalogo` admite empresa/país opcionales, filtros `desde`/`hasta`, `carpeta`, `tipo`, `contiene`, orden por fecha descendente y `limit`. Los permisos del usuario siempre se aplican.

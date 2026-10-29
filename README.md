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
1. Subir el repo a GitHub.
2. En Render: **New > Blueprint** y seleccionar el repo (usa `render.yaml`).
3. Configurar `OPENAI_API_KEY` en Environment (opcional; sin clave funciona en modo reglas).
4. Verificar `https://<servicio>.onrender.com/health` y probar `POST /chat`.

Comando de inicio: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## Preguntas de catálogo soportadas (tipo B)
`consultar_catalogo` acepta empresa/país opcionales, `carpeta`, `tipo`, `desde`/`hasta`, `contiene` y `limite`
(orden por fecha desc); los permisos siempre se aplican. Ej.: "¿Cuáles son los últimos documentos que se cargaron?",
"¿Qué documentos se añadieron o actualizaron en julio?", "¿Qué documentos mencionan \"garantías mobiliarias\"?".

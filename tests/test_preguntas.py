"""Pruebas del caso (modo reglas, sin OPENAI_API_KEY)."""
import pytest
from fastapi.testclient import TestClient

from app import tools
from app.agent import NO_ESTA, responder
from app.main import app

ADMIN = "ana.gerente"


@pytest.fixture(autouse=True)
def sin_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    tools.inicializar()


def test_1_efectivo_colombia():
    r = responder("¿Cuál es el monto máximo de efectivo permitido en una agencia de Prendia en Colombia?", ADMIN)
    assert "50.000.000" in r["respuesta"]
    assert all("/Colombia/" in f["link"] for f in r["fuentes"])


def test_2_bonos_peru():
    r = responder("¿Cuál es la política de bonos de Prendia en Perú?", ADMIN)
    assert "15%" in r["respuesta"] and "Chile" not in r["respuesta"]
    assert r["fuentes"] and all("/Peru/" in f["link"] for f in r["fuentes"])


def test_3_bonos_chile():
    r = responder("¿Cuál es la política de bonos de Prendia en Chile?", ADMIN)
    assert "semestral" in r["respuesta"] and "15%" not in r["respuesta"]
    assert all("/Chile/" in f["link"] for f in r["fuentes"])


def test_4_catalogo_cobranzas_prendia_peru():
    r = responder("¿Qué documentos de Cobranzas tiene Prendia en Perú?", ADMIN)
    titulos = {f["titulo"] for f in r["fuentes"]}
    assert titulos == {"Procedimiento de cobranza preventiva y temprana", "Procedimiento de remate de prendas"}


def test_5_garantias_mobiliarias():
    r = responder("¿Qué dice la normativa de MicroAvanza Perú sobre garantías mobiliarias?", ADMIN)
    assert "SUNARP" in r["respuesta"]
    assert "Constitución de garantías mobiliarias" in r["respuesta"]


def test_vacaciones_pide_aclaracion():
    r = responder("¿Cuál es la política de vacaciones?", ADMIN)
    assert "empresa" in r["respuesta"] and not r["fuentes"]


def test_no_esta_en_normativa():
    r = responder("¿Cuál es la política de teletrabajo de Prendia en Perú?", ADMIN)
    assert r["respuesta"] == NO_ESTA


def test_usuario_sin_permiso_no_ve_doc_restringido():
    pregunta = "¿Qué dice la política de remuneraciones ejecutivas del Corporativo?"
    r = responder(pregunta, "luis.analista")
    assert "remuneraciones" not in r["respuesta"].lower() and not r["fuentes"]
    # Control positivo: el Directorio sí lo ve
    assert responder(pregunta, "pedro.directorio")["fuentes"]


def test_api_health_y_chat(monkeypatch):
    monkeypatch.setenv("WATCH", "0")
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
        r = c.post("/chat", json={"prompt": "bonos Prendia Chile", "usuario": ADMIN})
        assert r.status_code == 200 and r.json()["fuentes"]


def test_b_ultimos_documentos_cargados():
    r = responder("¿Cuáles son los últimos documentos que se cargaron?", ADMIN)
    assert "2026-07-12" in r["respuesta"]
    assert len(r["fuentes"]) == 5


def test_b_documentos_julio():
    r = responder("¿Qué documentos se añadieron o actualizaron en julio?", ADMIN)
    titulos = {f["titulo"] for f in r["fuentes"]}
    assert "Código de ética y conducta" in titulos
    assert "Política de remuneraciones ejecutivas" in titulos


def test_b_carpeta_cobranzas_prendia():
    r = responder("Dame los documentos de la carpeta de Cobranzas de Prendia.", ADMIN)
    links = " ".join(f["link"] for f in r["fuentes"])
    assert "/Prendia/Peru/Cobranzas/" in links
    assert "/Prendia/Colombia/Cobranzas/" in links
    assert "/Prendia/Chile/Cobranzas/" in links


def test_b_procedimientos_colombia_este_ano():
    r = responder("¿Qué procedimientos de Colombia se actualizaron este año?", ADMIN)
    titulos = {f["titulo"] for f in r["fuentes"]}
    assert "Límite de efectivo en agencias" in titulos
    assert all("/Colombia/" in f["link"] for f in r["fuentes"])


def test_b_documentos_mencionan_garantias():
    r = responder("¿Qué documentos mencionan 'garantías mobiliarias'?", ADMIN)
    assert any("garant" in f["titulo"].lower() for f in r["fuentes"])


def test_b_efectivo_colombia_sin_empresa():
    r = responder("¿Cuál es el monto máximo de efectivo en una agencia de Colombia?", ADMIN)
    assert "50.000.000" in r["respuesta"]
    assert any("Prendia" in f["link"] for f in r["fuentes"])


def test_b_compara_bonificaciones_peru_chile():
    r = responder("Compara la política de bonificaciones de Perú y de Chile.", ADMIN)
    assert "15%" in r["respuesta"]
    assert "semestral" in r["respuesta"]
    assert any("/Peru/" in f["link"] for f in r["fuentes"])
    assert any("/Chile/" in f["link"] for f in r["fuentes"])


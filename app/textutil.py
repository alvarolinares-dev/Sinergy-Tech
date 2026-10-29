"""Utilidades de texto: normalización sin tildes y tokenización simple."""
import re
import unicodedata

STOPWORDS = set("""el la los las un una unos unas de del al a en y o que cual cuales cuál es son
por para con sin sobre se su sus lo le les como cuanto cuantos mi me nos
dice dicen normativa politica politicas procedimiento documento documentos tiene tienen
hay segun entre esta este estos estas ese esa ser cuando donde quien muy mas
compara comparar comparacion diferencia dame muestra empresa pais grupo altamar prendia microavanza autofacil corporativo peru colombia chile
""".split())


def norm(texto: str) -> str:
    """Minúsculas y sin tildes (la ñ se conserva)."""
    texto = texto.lower().replace("ñ", "\0")
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return texto.replace("\0", "ñ")


def _stem(tok: str) -> str:
    # "Stemming" mínimo: plural -> singular
    return tok[:-1] if len(tok) > 4 and tok.endswith("s") else tok


# Sinónimos simples (bonificaciones/incentivos -> bono)
SINONIMOS = {"bonificacione": "bono", "bonificacion": "bono", "incentivo": "bono"}


def tokenizar(texto: str, quitar_stop: bool = False) -> list[str]:
    toks = re.findall(r"[a-zñ0-9]+", norm(texto))
    if quitar_stop:
        toks = [t for t in toks if t not in STOPWORDS and len(t) > 2]
    return [SINONIMOS.get(_stem(t), _stem(t)) for t in toks]

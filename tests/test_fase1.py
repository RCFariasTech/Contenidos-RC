"""Tests sin red de los módulos de la Fase 1."""

import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from rc import prompts
from rc.esquema import CAMPOS_TEXTO, ESQUEMA_PIEZA
from rc.generador import _json_del_ultimo_texto, _sumar_uso, urls_de_busqueda


class TestEsquema(unittest.TestCase):
    def test_formatos_y_campos_obligatorios(self):
        for formato, campos in CAMPOS_TEXTO.items():
            esquema = ESQUEMA_PIEZA[formato]
            self.assertEqual(esquema["properties"]["formato"]["enum"], [formato])
            self.assertFalse(esquema["additionalProperties"])
            for c in campos:
                self.assertIn(c, esquema["required"])
            self.assertEqual(set(esquema["required"]), set(esquema["properties"]))


class TestPrompts(unittest.TestCase):
    def test_sistema_incluye_cta_y_temas_usados(self):
        texto = prompts.sistema()
        self.assertIn("📲 Síguenos para más ideas que conectan data, experiencia y negocio.", texto)
        self.assertIn("Marketing sensorial", texto)
        self.assertNotIn("$", texto)

    def test_generar_sin_historial(self):
        slot = {"semana": 2, "formato": "Reel", "tipo": "Tendencia", "pilar": "Tendencias de marketing BTL"}
        texto = prompts.generar(slot, [], [])
        self.assertIn("Formato: Reel", texto)
        self.assertIn("(sin registros)", texto)

    def test_resumen_de_historial(self):
        historial = [{"mes": "2026-10", "pilar": "BTL",
                      "contenido": {"tema_especifico": "Sampling",
                                    "investigacion": {"tendencia": "T", "estrategia_clave": "E"}}}]
        texto = prompts.generar({"semana": 1, "formato": "Carrusel", "tipo": "x", "pilar": "y"}, historial, [])
        self.assertIn("- 2026-10 | BTL | Sampling | T | E", texto)


class TestRespuestaClaude(unittest.TestCase):
    def test_urls_de_busqueda_ignora_errores(self):
        contenido = [
            SimpleNamespace(type="server_tool_use"),
            SimpleNamespace(type="web_search_tool_result",
                            content=[SimpleNamespace(url="https://a.com/x"), SimpleNamespace(url="https://b.com")]),
            SimpleNamespace(type="web_search_tool_result",
                            content=SimpleNamespace(error_code="max_uses_exceeded")),
            SimpleNamespace(type="text", text="{}"),
        ]
        self.assertEqual(urls_de_busqueda(contenido), ["https://a.com/x", "https://b.com"])

    def test_json_del_ultimo_texto(self):
        contenido = [SimpleNamespace(type="text", text="preámbulo"),
                     SimpleNamespace(type="text", text='```json\n{"a": 1}\n```')]
        self.assertEqual(_json_del_ultimo_texto(contenido), {"a": 1})

    def test_sumar_uso(self):
        total = {}
        _sumar_uso(total, SimpleNamespace(model_dump=lambda: {
            "input_tokens": 10, "output_tokens": 5, "server_tool_use": {"web_search_requests": 2}}))
        _sumar_uso(total, SimpleNamespace(model_dump=lambda: {"input_tokens": 1, "output_tokens": 1}))
        self.assertEqual(total["input_tokens"], 11)
        self.assertEqual(total["web_search_requests"], 2)


class TestRouter(unittest.TestCase):
    def _llamar(self, ruta, metodo="GET", cabeceras=None):
        from api.index import handler
        h = handler.__new__(handler)
        h.path = f"/api/index?ruta={ruta}"
        h.headers = cabeceras or {}
        h.rfile = io.BytesIO(b"")
        h.wfile = io.BytesIO()
        estados = []
        h.send_response = lambda e: estados.append(e)
        h.send_header = lambda *a: None
        h.end_headers = lambda: None
        h._atender(metodo)
        return estados[0], json.loads(h.wfile.getvalue())

    def test_salud(self):
        self.assertEqual(self._llamar("salud"), (200, {"ok": True}))

    def test_ruta_inexistente(self):
        self.assertEqual(self._llamar("nada")[0], 404)

    def test_diagnostico_sin_secreto(self):
        with mock.patch.dict(os.environ, {"CRON_SECRET": "s3creto"}):
            self.assertEqual(self._llamar("diagnostico")[0], 401)
            self.assertEqual(self._llamar("diagnostico", cabeceras={"Authorization": "Bearer otro"})[0], 401)

    def test_yo_sin_token(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x", "SUPABASE_ANON_KEY": "a", "OWNER_EMAIL": "o@x"}):
            self.assertEqual(self._llamar("yo")[0], 401)


if __name__ == "__main__":
    unittest.main()

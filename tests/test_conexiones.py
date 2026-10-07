"""Verificación de la clave de Anthropic sin generar contenido (sin red)."""

import unittest
from unittest import mock

import anthropic
import httpx2 as httpx  # el SDK de anthropic usa httpx2

from rc import generador


def _error(clase, codigo):
    req = httpx.Request("GET", "https://api.anthropic.com/v1/models")
    return clase("x", response=httpx.Response(codigo, request=req), body=None)


class TestVerificarClave(unittest.TestCase):
    def test_pista_sin_revelar_la_clave(self):
        clave = "sk-ant-api03-" + "x" * 90
        pista = generador._pista_clave(clave)
        self.assertIn("clave de API (correcto)", pista)
        self.assertIn(str(len(clave)), pista)
        self.assertNotIn("xxxx", pista)
        self.assertIn("ADMINISTRACIÓN", generador._pista_clave("sk-ant-admin01-abc"))
        self.assertIn("no tiene el formato", generador._pista_clave("krea-token"))

    def test_sin_clave(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(generador.verificar_clave()["ok"], False)

    def test_clave_valida_solo_lista_modelos(self):
        cliente = mock.MagicMock()
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(generador, "_cliente", return_value=cliente):
            self.assertEqual(generador.verificar_clave(), {"ok": True, "detalle": "Clave válida."})
        cliente.models.list.assert_called_once_with(limit=1)
        cliente.messages.create.assert_not_called()

    def test_la_clave_se_usa_sin_espacios_ni_saltos_de_linea(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "  sk-ant-prueba\n"}):
            self.assertEqual(generador._cliente().api_key, "sk-ant-prueba")

    def test_clave_invalida(self):
        cliente = mock.MagicMock()
        cliente.models.list.side_effect = _error(anthropic.AuthenticationError, 401)
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(generador, "_cliente", return_value=cliente):
            r = generador.verificar_clave()
        self.assertFalse(r["ok"])
        self.assertIn("no reconoce la clave", r["detalle"])


if __name__ == "__main__":
    unittest.main()

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
    def test_sin_clave(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(generador.verificar_clave()["ok"], False)

    def test_clave_valida_solo_lista_modelos(self):
        cliente = mock.MagicMock()
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(generador, "_cliente", return_value=cliente):
            self.assertEqual(generador.verificar_clave(), {"ok": True, "detalle": "Clave válida."})
        cliente.models.list.assert_called_once_with(limit=1)
        cliente.messages.create.assert_not_called()

    def test_clave_invalida(self):
        cliente = mock.MagicMock()
        cliente.models.list.side_effect = _error(anthropic.AuthenticationError, 401)
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(generador, "_cliente", return_value=cliente):
            r = generador.verificar_clave()
        self.assertFalse(r["ok"])
        self.assertIn("no reconoce la clave", r["detalle"])


if __name__ == "__main__":
    unittest.main()

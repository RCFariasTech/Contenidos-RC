"""Cliente de Krea y tamaños/colores de las ilustraciones (sin red)."""

import io
import json
import unittest
import urllib.error
from unittest import mock

from rc import krea, tarjetas
from rc.errores import ErrorNegocio


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestKrea(unittest.TestCase):
    def test_crear_trabajo_envia_el_lora_al_endpoint_de_flux(self):
        capturado = {}

        def urlopen(req, timeout=None):
            capturado.update(url=req.full_url, auth=req.get_header("Authorization"), cuerpo=json.loads(req.data))
            return Resp(json.dumps({"job_id": "abc"}).encode())

        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(krea.crear_trabajo("un prompt", 1216, 864), "abc")
        self.assertEqual(capturado["url"], "https://api.krea.ai/generate/image/bfl/flux-1-dev")
        self.assertEqual(capturado["auth"], "Bearer tok")
        c = capturado["cuerpo"]
        self.assertEqual((c["width"], c["height"], c["prompt"]), (1216, 864, "un prompt"))
        self.assertEqual(c["styles"], [{"id": "kq4b7fium", "strength": 1}])

    def test_consultar_interpreta_los_estados(self):
        def respuesta(cuerpo):
            return mock.patch("urllib.request.urlopen", lambda req, timeout=None: Resp(json.dumps(cuerpo).encode()))

        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}):
            with respuesta({"status": "completed", "result": {"urls": ["https://gen.krea.ai/images/a.png"]}}):
                self.assertEqual(krea.consultar("j")["url"], "https://gen.krea.ai/images/a.png")
            with respuesta({"status": "sampling"}):
                self.assertEqual(krea.consultar("j")["estado"], "en_cola")
            with respuesta({"status": "failed", "error": {"message": "boom"}}):
                self.assertEqual(krea.consultar("j"), {"estado": "fallida", "url": None, "error": "boom"})
            with respuesta({"status": "completed", "result": {"urls": ["http://inseguro/x.png"]}}):
                self.assertEqual(krea.consultar("j")["estado"], "fallida")  # solo se aceptan URLs https

    def test_errores_http_con_mensaje_claro(self):
        for codigo, texto in ((401, "clave"), (402, "saldo de API"), (429, "demasiados")):
            def urlopen(req, timeout=None, c=codigo):
                raise urllib.error.HTTPError(req.full_url, c, "x", {}, io.BytesIO(b"{}"))
            with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
                with self.assertRaises(ErrorNegocio) as ctx:
                    krea.crear_trabajo("p", 512, 512)
            self.assertIn(texto, str(ctx.exception))

    def test_el_error_400_incluye_el_motivo_de_krea(self):
        def urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(b'{"error": "style kq4b7fium not found"}'))
        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(ErrorNegocio) as ctx:
                krea.crear_trabajo("p", 512, 512)
        self.assertEqual(str(ctx.exception), "Krea rechazó la solicitud (400): style kq4b7fium not found")

    def test_sin_token_no_llama_a_krea(self):
        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": ""}):
            self.assertFalse(krea.configurado())
            with self.assertRaises(ErrorNegocio):
                krea.crear_trabajo("p", 512, 512)

    def test_prompt_incluye_fondo_y_bordes_difuminados(self):
        p = krea.construir_prompt("Two 3D characters shaking hands.", "azul_marino", "#1F3864")
        self.assertIn("deep navy blue (#1F3864)", p)
        self.assertIn("edges of the image blur softly and fade into the background color", p)
        self.assertLessEqual(len(p), 1800)


class TestTamanosYFondos(unittest.TestCase):
    def test_tamanos_multiplos_de_16_dentro_del_rango_de_krea(self):
        for estilo in tarjetas.AREA_ILUSTRACION:
            ancho, alto = tarjetas.tamano_ilustracion(estilo)
            self.assertTrue(ancho % 16 == 0 and alto % 16 == 0 and 512 <= min(ancho, alto) and max(ancho, alto) <= 2368)
            w, h = tarjetas.AREA_ILUSTRACION[estilo]
            self.assertAlmostEqual(ancho / alto, w / h, delta=0.05)

    def test_el_fondo_pedido_coincide_con_el_de_la_tarjeta(self):
        for variante in range(6):
            for semilla in range(3):
                est = tarjetas.estilos_sugeridos(variante, semilla)
                clave1, hex1 = tarjetas.fondo_de_tarjeta(1, variante, semilla)
                self.assertEqual(clave1, tarjetas.PORTADAS[(variante + semilla) % len(tarjetas.PORTADAS)][0])
                clave2, _ = tarjetas.fondo_de_tarjeta(2, variante, semilla)
                self.assertEqual(clave2, tarjetas.FONDO_ESTILO[est[1]])
                self.assertRegex(hex1, r"^#[0-9A-Fa-f]{6}$")


if __name__ == "__main__":
    unittest.main()

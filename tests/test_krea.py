"""Cliente de Krea y prompts de íconos y fotos (sin red)."""

import io
import json
import unittest
import urllib.error
from unittest import mock

from rc import krea
from rc.errores import ErrorNegocio


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestKrea(unittest.TestCase):
    def test_crear_trabajo_usa_nano_banana_con_referencias(self):
        capturado = {}

        def urlopen(req, timeout=None):
            capturado.update(url=req.full_url, auth=req.get_header("Authorization"), cuerpo=json.loads(req.data))
            return Resp(json.dumps({"job_id": "abc"}).encode())

        refs = ["https://contenidos-rc.vercel.app/marca/iso/iso_2.png", "http://inseguro/x.png"]
        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(krea.crear_trabajo("un prompt", "1:1", refs), "abc")
        self.assertEqual(capturado["url"], "https://api.krea.ai/generate/image/google/nano-banana-pro")
        self.assertEqual(capturado["auth"], "Bearer tok")
        self.assertEqual(capturado["cuerpo"], {"prompt": "un prompt", "aspect_ratio": "1:1", "resolution": "1K",
                                               "image_urls": [refs[0]]})  # solo URLs https

    def test_foto_sin_referencias(self):
        self.assertNotIn("image_urls", krea.cuerpo_generacion("p", "16:9"))

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
                    krea.crear_trabajo("p", "1:1")
            self.assertIn(texto, str(ctx.exception))

    def test_el_error_400_incluye_el_motivo_de_krea(self):
        def urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(b'{"error": "style kq4b7fium not found"}'))
        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(ErrorNegocio) as ctx:
                krea.crear_trabajo("p", "1:1")
        self.assertEqual(str(ctx.exception), "Krea rechazó la solicitud (400): style kq4b7fium not found")

    def test_motivo_de_rechazo_en_cualquier_formato(self):
        self.assertEqual(krea._motivo('{"error": "estilo no encontrado"}'), "estilo no encontrado")
        self.assertEqual(krea._motivo('{"message": "bad width"}'), "bad width")
        self.assertEqual(krea._motivo('{"detail": [{"loc": ["body", "styles"], "msg": "invalid"}]}'),
                         '[{"loc": ["body", "styles"], "msg": "invalid"}]')
        self.assertEqual(krea._motivo('{"otra": 1}'), '{"otra": 1}')
        self.assertEqual(krea._motivo("texto plano\ncon saltos"), "texto plano con saltos")
        self.assertEqual(krea._motivo(""), "")

    def test_sin_token_no_llama_a_krea(self):
        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": ""}):
            self.assertFalse(krea.configurado())
            with self.assertRaises(ErrorNegocio):
                krea.crear_trabajo("p", "1:1")

    def test_prompt_de_icono_con_el_estilo_de_la_guia(self):
        p = krea.construir_prompt("a shelf with a screen and a cart.", "icono")
        self.assertIn("Subject: a shelf with a screen and a cart.", p)
        for rasgo in ("isometric", "#005EFF", "#FF0006", "flat solid navy #12244A", "No text"):
            self.assertIn(rasgo, p)

    def test_prompt_de_foto_realista_de_clase_media(self):
        p = krea.construir_prompt("a woman in a supermarket aisle", "foto")
        for rasgo in ("documentary", "a woman in a supermarket aisle", "Middle-class", "well-groomed",
                      "five fingers", "not fashion models"):
            self.assertIn(rasgo, p)

    def test_referencias_de_iconos_publicas(self):
        from rc import estilo_iconos
        refs = estilo_iconos.referencias_icono("https://contenidos-rc.vercel.app/")
        self.assertTrue(refs and all(r.startswith("https://contenidos-rc.vercel.app/marca/iso/") for r in refs))
        from rc.config import RAIZ
        for r in estilo_iconos.REFERENCIAS_ICONO:
            self.assertTrue((RAIZ / "public" / r.lstrip("/")).exists(), r)


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(c["styles"], [{"id": "p19ubhgd5", "strength": 1}])

    def test_parametros_para_krea_2(self):
        from rc.config import ajustes
        k = dict(ajustes()["krea"], modelo="krea/krea-2/medium")
        with mock.patch.dict(ajustes(), {"krea": k}):
            c = krea.cuerpo_generacion("p", 1216, 848)
        self.assertEqual((c["aspect_ratio"], c["resolution"], c["creativity"]), ("3:2", "1K", "raw"))
        self.assertNotIn("width", c)
        self.assertEqual(c["styles"], [{"id": "p19ubhgd5", "strength": 1}])
        self.assertEqual(krea.proporcion_cercana(410, 880), "9:16")

    def test_referencias_de_estilo_solo_si_estan_configuradas(self):
        from rc.config import ajustes
        self.assertNotIn("image_style_references", krea.cuerpo_generacion("p", 1216, 848))  # hoy: solo el LoRA
        k = dict(ajustes()["krea"], referencias_estilo=["https://gen.krea.ai/images/a.png"], fuerza_referencias=0.3)
        with mock.patch.dict(ajustes(), {"krea": k}):
            refs = krea.cuerpo_generacion("p", 1216, 848)["image_style_references"]
        self.assertEqual(refs, [{"url": "https://gen.krea.ai/images/a.png", "strength": 0.3}])

    def test_envia_la_guia_de_composicion(self):
        c = krea.cuerpo_generacion("p", 912, 1216, guia="https://app/api/guia-composicion?estilo=1")
        self.assertEqual(c["image_url"], "https://app/api/guia-composicion?estilo=1")
        self.assertEqual(c["strength"], 0.88)
        self.assertNotIn("image_url", krea.cuerpo_generacion("p", 912, 1216))

    def test_si_krea_rechaza_el_boceto_reintenta_sin_el(self):
        cuerpos = []

        def urlopen(req, timeout=None):
            cuerpos.append(json.loads(req.data))
            if "image_url" in cuerpos[-1]:
                raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(b'{"error": "bad image"}'))
            return Resp(json.dumps({"job_id": "ok"}).encode())

        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(krea.crear_trabajo("p", 912, 1216, "https://app/guia.png"), "ok")
        self.assertEqual(["image_url" in c for c in cuerpos], [True, False])

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

    def test_sin_acceso_al_modelo_sugiere_clave_personal(self):
        def urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(b'{"error": "Invalid ids detected or no access"}'))
        with mock.patch.dict("os.environ", {"KREA_API_TOKEN": "tok"}), mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(ErrorNegocio) as ctx:
                krea.crear_trabajo("p", 512, 512)
        self.assertIn("PERSONAL", str(ctx.exception))

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
                krea.crear_trabajo("p", 512, 512)

    def test_prompt_corto_al_estilo_de_las_sesiones_de_rc(self):
        self.assertTrue(krea.construir_prompt("3d of a robot waving his hand.", "gris_claro")
                        .startswith("3d of a robot waving his hand, isolated in a flat solid light gray background"))
        self.assertTrue(krea.construir_prompt("A character consulting a laptop", "coral")
                        .startswith("3d of a character consulting a laptop, isolated in a flat solid red background"))
        # si la escena ya traía un fondo, manda el de la tarjeta
        self.assertTrue(krea.construir_prompt("3d of a kid, isolated in a white background", "azul_medio")
                        .startswith("3d of a kid, isolated in a flat solid blue background"))


class TestTamanosYFondos(unittest.TestCase):
    def test_la_ilustracion_se_genera_del_tamano_de_la_tarjeta(self):
        ancho, alto = tarjetas.tamano_ilustracion()
        self.assertEqual((ancho, alto), (912, 1216))                      # 3:4, múltiplos de 16
        self.assertAlmostEqual(ancho / alto, tarjetas.W / tarjetas.H, delta=0.01)

    def test_composicion_deja_libre_la_zona_del_texto(self):
        p = krea.construir_prompt("3d of a robot", "coral", composicion=tarjetas.COMPOSICION[1])
        self.assertTrue(p.startswith("3d of a robot, with the characters in the upper half of the image and the bottom "
                                     "half of the image empty, isolated in a flat solid red background"))
        self.assertIn("no floor line", p)
        self.assertIn("minimal soft contact shadow", p)
        self.assertEqual(set(tarjetas.COMPOSICION), set(tarjetas.ZONAS_TEXTO))

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

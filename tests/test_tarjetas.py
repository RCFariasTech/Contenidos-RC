"""Tarjetas de carrusel en PDF 3:4 (sin red)."""

import json
import unittest
from pathlib import Path

import pymupdf  # solo para verificar el PDF en pruebas

from rc import tarjetas
from tests.test_logica import carrusel

FIXTURE = Path(__file__).parent / "fixtures" / "mes_noviembre.json"


class TestTarjetas(unittest.TestCase):
    def test_pdf_de_cinco_paginas_3_4_con_texto_vivo(self):
        pieza = carrusel()
        doc = pymupdf.open(stream=tarjetas.generar_pdf(pieza), filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (1080, 1440))
        self.assertIn("Tu góndola ya es un medio", " ".join(doc[0].get_text().split()))
        self.assertIn("Constellation", doc[4].get_text())

    def test_contenido_viejo_sin_diseno(self):
        datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pieza = next(p["contenido"] for p in datos["piezas"] if p["formato"] == "Carrusel")
        self.assertNotIn("diseno", pieza)
        tarjs = tarjetas.datos_tarjetas(pieza)
        self.assertEqual(len(tarjs), 5)
        self.assertEqual(tarjs[0]["titular"], pieza["slide_1_gancho"])
        self.assertEqual(len(pymupdf.open(stream=tarjetas.generar_pdf(pieza), filetype="pdf")), 5)

    def test_estilos_varian_entre_carruseles(self):
        a, b = tarjetas.estilos_sugeridos(0), tarjetas.estilos_sugeridos(1)
        self.assertEqual((a[0], a[-1], b[0], b[-1]), (1, 7, 1, 7))
        self.assertNotEqual(a[1:4], b[1:4])

    def test_solo_las_tarjetas_1_y_2_llevan_ilustracion(self):
        for v in range(12):
            est = tarjetas.estilos_sugeridos(v)
            self.assertIn(est[1], tarjetas.ESTILOS_CON_ILUSTRACION)
            self.assertTrue(all(e not in tarjetas.ESTILOS_CON_ILUSTRACION for e in est[2:]), est)
        doc = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), variante=3, guias=True), filetype="pdf")
        con = [i + 1 for i, p in enumerate(doc) if "ILUSTRACIÓN 3D" in p.get_text()]
        self.assertEqual(con, [1, 2])

    def test_la_descarga_no_trae_recuadros_de_ilustracion_solo_la_vista_previa(self):
        previa = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), guias=True), filetype="pdf")
        descarga = pymupdf.open(stream=tarjetas.generar_pdf(carrusel()), filetype="pdf")
        self.assertTrue(any("ILUSTRACIÓN 3D" in p.get_text() for p in previa))
        self.assertFalse(any("ILUSTRACIÓN 3D" in p.get_text() or "Krea" in p.get_text() for p in descarga))
        self.assertIn("Tu góndola", " ".join(descarga[0].get_text().split()))  # el texto sigue ahí

    def test_rehacer_cambia_la_propuesta(self):
        propuestas = {tuple(tarjetas.estilos_sugeridos(2, s)) for s in range(6)}
        self.assertGreaterEqual(len(propuestas), 4)
        for s in range(8):
            est = tarjetas.estilos_sugeridos(2, s)
            self.assertIn(est[1], tarjetas.ESTILOS_CON_ILUSTRACION)
            self.assertTrue(all(e not in tarjetas.ESTILOS_CON_ILUSTRACION for e in est[2:4]))
        self.assertEqual(tarjetas.estilos_sugeridos(2, 0), tarjetas.estilos_sugeridos(2))
        pdf0 = tarjetas.generar_pdf(carrusel(), variante=2, semilla=0)
        pdf1 = tarjetas.generar_pdf(carrusel(), variante=2, semilla=1)
        self.assertNotEqual(pdf0, pdf1)

    def test_portadas_rotan_de_color(self):
        fondos = [tarjetas.PORTADAS[v % len(tarjetas.PORTADAS)][0] for v in range(5)]
        self.assertEqual(len(set(fondos)), 5)
        # carruseles consecutivos (mismo mes o mes siguiente) nunca repiten fondo
        self.assertTrue(all(fondos[i] != fondos[(i + 1) % 5] for i in range(5)))

    def test_todo_el_texto_cabe_dentro_de_la_tarjeta_sin_solaparse(self):
        """Textos extremos en los 7 estilos: nada se sale de la página ni se pisa con otro texto."""
        import random
        rnd = random.Random(7)
        lex = ("activación retail media experiencia consumidor marca estrategia incremental conversión "
               "audiencia segmentación medición omnicanalidad personalización sostenibilidad").split()

        def frase(n):
            return " ".join(rnd.choice(lex) for _ in range(n))

        for _ in range(12):
            tarjs = [{"titular": frase(rnd.randint(1, 14)), "texto": frase(rnd.randint(0, 55)),
                      "nota": frase(rnd.randint(3, 40)), "variante": rnd.randint(0, 9)} for _ in range(9)]
            for estilo, fn in tarjetas.ESTILOS.items():
                import io
                from reportlab.pdfgen import canvas
                tarjetas._registrar_fuentes()
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=(tarjetas.W, tarjetas.H))
                fn(tarjetas.Lienzo(c, tarjetas._colores()), tarjs[estilo - 1])
                c.showPage()
                c.save()
                pagina = pymupdf.open(stream=buf.getvalue(), filetype="pdf")[0]
                lineas = [pymupdf.Rect(ln["bbox"]) for b in pagina.get_text("dict")["blocks"] if b["type"] == 0
                          for ln in b["lines"]]
                for r in lineas:
                    self.assertTrue(pymupdf.Rect(20, 20, tarjetas.W - 20, tarjetas.H - 20).contains(r),
                                    f"estilo {estilo}: texto fuera de la tarjeta {r}")
                for i, a in enumerate(lineas):
                    for b in lineas[i + 1:]:
                        inter = a & b
                        self.assertFalse(inter.width > 3 and inter.height > 0.4 * min(a.height, b.height),
                                         f"estilo {estilo}: textos superpuestos {a} / {b}")

    def test_orden_de_lectura_titular_antes_que_texto(self):
        """En cada estilo con titular y texto, el titular queda arriba del texto (se lee primero)."""
        import io
        from reportlab.pdfgen import canvas
        tarjetas._registrar_fuentes()
        d = {"titular": "ALFATITULAR completo aquí.", "texto": "OMEGATEXTO sigue después.", "nota": "x", "variante": 0}
        for estilo, fn in tarjetas.ESTILOS.items():
            if estilo == 7:
                continue
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(tarjetas.W, tarjetas.H))
            fn(tarjetas.Lienzo(c, tarjetas._colores()), d)
            c.showPage()
            c.save()
            pagina = pymupdf.open(stream=buf.getvalue(), filetype="pdf")[0]
            y = {}
            for clave in ("ALFATITULAR", "OMEGATEXTO"):
                y[clave] = pagina.search_for(clave)[0].y0
            self.assertLess(y["ALFATITULAR"], y["OMEGATEXTO"], f"estilo {estilo}: el texto aparece antes que el titular")

    def test_contenido_viejo_usa_la_primera_oracion_como_titular(self):
        tit, texto = tarjetas._separar("El 78% admite que al menos el 10% de su presupuesto se desperdicia por medición débil. "
                                       "En BTL, impactos y muestras no responden al comité financiero.")
        self.assertEqual(tit, "El 78% admite que al menos el 10% de su presupuesto se desperdicia por medición débil")
        self.assertTrue(texto.startswith("En BTL"))
        tit, texto = tarjetas._separar("Menos presupuesto perdido: medir cada activación cambia la conversación con finanzas.")
        self.assertEqual((tit, texto.startswith("medir")), ("Menos presupuesto perdido", True))
        tit, texto = tarjetas._separar("Una sola oración sin corte natural que sigue y sigue")
        self.assertEqual(texto, "")

    def test_ilustracion_a_sangre_se_funde_con_el_color_bajo_el_texto(self):
        import io
        from PIL import Image
        foto = Image.new("RGB", (912, 1216), (200, 30, 30))   # imagen de un color muy distinto al de la tarjeta
        buf = io.BytesIO()
        foto.save(buf, "PNG")
        compuesto = Image.open(io.BytesIO(tarjetas.fondo_con_ilustracion(buf.getvalue(), "#0069D1", tarjetas.ZONAS_TEXTO[1], escala=0.5)))
        w, h = compuesto.size
        self.assertEqual((w, h), (540, 720))                          # tarjeta completa
        arriba, abajo = compuesto.getpixel((w // 2, int(h * 0.2))), compuesto.getpixel((w // 2, int(h * 0.8)))
        self.assertGreater(arriba[0], 150)                            # arriba se ve la ilustración
        self.assertTrue(abs(abajo[0] - 0x00) < 12 and abs(abajo[2] - 0xD1) < 12)  # bajo el texto: color de la tarjeta

    def test_el_fondo_de_la_imagen_se_empata_con_el_color_de_la_tarjeta(self):
        from PIL import Image
        img = Image.new("RGB", (100, 100), (240, 85, 90))           # casi coral
        corregida = tarjetas._empatar_fondo(img, "#F65155")
        self.assertEqual(corregida.getpixel((50, 50)), (0xF6, 0x51, 0x55))
        lejos = Image.new("RGB", (100, 100), (250, 250, 250))       # fondo blanco en tarjeta coral: no se toca
        self.assertEqual(tarjetas._empatar_fondo(lejos, "#F65155").getpixel((5, 5)), (250, 250, 250))

    def test_tarjeta_con_ilustracion_no_dibuja_recuadro(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (912, 1216), (240, 240, 240)).save(buf, "PNG")
        doc = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), guias=True, imagenes={1: buf.getvalue()}), filetype="pdf")
        self.assertTrue(doc[0].get_images())
        self.assertNotIn("ILUSTRACIÓN 3D", doc[0].get_text())
        self.assertIn("ILUSTRACIÓN 3D", doc[1].get_text())           # la tarjeta 2 sin imagen conserva su guía
        self.assertIn("Tu góndola", " ".join(doc[0].get_text().split()))

    def test_nombre_de_archivo(self):
        self.assertEqual(tarjetas.nombre_archivo({"tema_especifico": "Retail media: ¿ya?"}, "2026-11-01"),
                         "tarjetas-2026-11-retail-media-ya.pdf")


if __name__ == "__main__":
    unittest.main()

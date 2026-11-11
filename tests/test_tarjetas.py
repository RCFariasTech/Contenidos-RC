"""Tarjetas de carrusel en PDF 4:5 · sistema gráfico 2026 (sin red)."""

import json
import unittest
from pathlib import Path

import pymupdf  # solo para verificar el PDF en pruebas

from rc import tarjetas
from tests.test_logica import carrusel

FIXTURE = Path(__file__).parent / "fixtures" / "mes_noviembre.json"


class TestTarjetas(unittest.TestCase):
    def test_pdf_de_cinco_paginas_4_5_con_texto_vivo(self):
        pieza = carrusel()
        doc = pymupdf.open(stream=tarjetas.generar_pdf(pieza), filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (1080, 1350))
        fuentes = {f[3] for f in doc[0].get_fonts()}
        self.assertTrue(any("SpaceGrotesk-Bold" in f for f in fuentes), fuentes)   # titular gancho en bold
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

    def test_orden_fijo_y_dato_o_icono_en_la_tarjeta_4(self):
        base = {"slide_1_gancho": "a", "slide_2": "b", "slide_3": "c", "slide_5_cierre": "e"}
        self.assertEqual(tarjetas.plantillas_de({**base, "slide_4": "Las ventas suben 18% con pantallas."}), [1, 2, 3, 4, 5])
        self.assertEqual(tarjetas.plantillas_de({**base, "slide_4": "Sin cifras aquí."}), [1, 2, 3, 3, 5])

    def test_elegir_que_cifra_resaltar(self):
        texto = "Regla 95-5: solo 5% compra ahora"
        self.assertEqual(tarjetas.candidatos_cifra(texto), ["95-5", "95", "5", "5%"])
        self.assertEqual(tarjetas.separar_cifra(texto, "5%"), ("Regla 95-5: solo", "5%", "compra ahora"))
        self.assertEqual(tarjetas.separar_cifra(texto, "5")[1], "5")
        self.assertEqual(tarjetas.separar_cifra(texto, "no está")[1], tarjetas.separar_cifra(texto)[1])
        pieza = {"slide_1_gancho": "a", "slide_2": "b", "slide_3": "c", "slide_4": texto, "slide_5_cierre": "e"}
        pagina = pymupdf.open(stream=tarjetas.generar_pdf(pieza, cifras={"4": "5%"}), filetype="pdf")[3]
        grandes = [s["text"].strip() for b in pagina.get_text("dict")["blocks"] if b["type"] == 0
                   for ln in b["lines"] for s in ln["spans"] if s["size"] > 150]
        self.assertEqual(grandes, ["5%"])

    def test_la_cifra_va_gigante_y_en_bold(self):
        pieza = {"slide_1_gancho": "a", "slide_2": "b", "slide_3": "c", "slide_5_cierre": "e",
                 "slide_4": "La comunicación en punto de venta sube en promedio 18% las ventas anunciadas."}
        self.assertEqual(tarjetas.separar_cifra(pieza["slide_4"])[1], "18%")
        pagina = pymupdf.open(stream=tarjetas.generar_pdf(pieza), filetype="pdf")[3]
        tramos = [s for b in pagina.get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for s in ln["spans"]]
        cifra = next(s for s in tramos if s["text"].strip() == "18%")
        self.assertGreater(cifra["size"], 150)
        self.assertIn("SpaceGrotesk-Bold", cifra["font"])

    def test_los_colores_rotan_por_semana(self):
        self.assertEqual([tarjetas.color_de_tarjeta(1, tarjetas.inicio_de_semana(s)) for s in (1, 2, 3, 4)],
                         ["marino", "azul", "gris", "rojo2"])                  # cada semana empieza con otro color
        self.assertEqual([tarjetas.color_de_tarjeta(n, 1) for n in range(1, 6)],
                         ["azul", "gris", "rojo2", "marino", "azul"])         # y las tarjetas siguen el mismo orden
        for inicio, esperado in ((0, (0x12, 0x24, 0x4A)), (2, (0xC9, 0xCA, 0xCB))):
            pix = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), inicio=inicio), filetype="pdf")[0] \
                .get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
            self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(pix.pixel(2, 2), esperado)))

    def test_icono_de_linea_elegido_o_alternativo(self):
        claves = tarjetas.iconos_linea()
        self.assertGreaterEqual(len(claves), 10)
        self.assertEqual(tarjetas._icono_de({"icono": "crecimiento"}, 0), "crecimiento")
        self.assertIn(tarjetas._icono_de({"icono": "inexistente"}, 3), claves)

    def test_la_descarga_no_trae_recuadros_de_imagen_solo_la_vista_previa(self):
        previa = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), guias=True), filetype="pdf")
        descarga = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), guias=False), filetype="pdf")
        self.assertIn("ÍCONO ISOMÉTRICO", previa[0].get_text())
        self.assertIn("FOTO", previa[1].get_text())
        self.assertNotIn("ÍCONO ISOMÉTRICO", descarga[0].get_text())
        self.assertNotIn("FOTO", descarga[1].get_text())

    def test_todo_el_texto_cabe_dentro_de_la_tarjeta_sin_solaparse(self):
        """Textos extremos en las 5 plantillas: nada se sale de la página ni se pisa con otro texto."""
        import random
        rnd = random.Random(7)
        lex = ("activación retail media experiencia consumidor marca estrategia incremental conversión "
               "audiencia segmentación medición omnicanalidad personalización sostenibilidad").split()

        def frase(n):
            return " ".join(rnd.choice(lex) for _ in range(n))

        for _ in range(12):
            tarjs = [{"titular": frase(rnd.randint(1, 14)), "texto": frase(rnd.randint(0, 55)),
                      "nota": frase(rnd.randint(3, 40)), "alternativa": rnd.randint(0, 9)} for _ in range(9)]
            for estilo, fn in tarjetas.PLANTILLAS.items():
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
                          for ln in b["lines"]
                          if "".join(s["text"] for s in ln["spans"]).strip() != "\u201d"]  # comillas decorativas
                for r in lineas:
                    self.assertTrue(pymupdf.Rect(20, 20, tarjetas.W - 20, tarjetas.H - 20).contains(r),
                                    f"estilo {estilo}: texto fuera de la tarjeta {r}")
                for i, a in enumerate(lineas):
                    for b in lineas[i + 1:]:
                        inter = a & b
                        self.assertFalse(inter.width > 3 and inter.height > 0.4 * min(a.height, b.height),
                                         f"estilo {estilo}: textos superpuestos {a} / {b}")

    def test_contenido_viejo_usa_la_primera_oracion_como_titular(self):
        tit, texto = tarjetas._separar("El 78% admite que al menos el 10% de su presupuesto se desperdicia por medición débil. "
                                       "En BTL, impactos y muestras no responden al comité financiero.")
        self.assertEqual(tit, "El 78% admite que al menos el 10% de su presupuesto se desperdicia por medición débil")
        self.assertTrue(texto.startswith("En BTL"))
        tit, texto = tarjetas._separar("Menos presupuesto perdido: medir cada activación cambia la conversación con finanzas.")
        self.assertEqual((tit, texto.startswith("medir")), ("Menos presupuesto perdido", True))
        tit, texto = tarjetas._separar("Una sola oración sin corte natural que sigue y sigue")
        self.assertEqual(texto, "")

    def _foto(self, caja, fondo=(240, 85, 90)):
        import io
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (912, 1216), fondo)
        ImageDraw.Draw(img).rectangle([caja[0] * 912, caja[1] * 1216, caja[2] * 912, caja[3] * 1216], fill=(30, 60, 200))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def test_el_icono_se_funde_con_el_fondo_marino(self):
        foto = self._foto((0.3, 0.3, 0.7, 0.7), fondo=(20, 38, 76))   # Krea no clava el marino exacto
        self.assertEqual(tarjetas.color_fondo_imagen(foto), "#14264C")
        doc = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), imagenes={1: foto}), filetype="pdf")
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
        self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(pix.pixel(2, 2), (20, 38, 76))))
        rojo = self._foto((0.3, 0.3, 0.7, 0.7), fondo=(240, 85, 90))   # fondo muy distinto: se mantiene el marino
        pix = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), imagenes={1: rojo}), filetype="pdf")[0] \
            .get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
        self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(pix.pixel(2, 2), (0x12, 0x24, 0x4A))))

    def test_icono_de_linea_generado_en_la_tarjeta_3(self):
        icono = self._foto((0.3, 0.3, 0.7, 0.7), fondo=(0xC8, 0xC9, 0xCA))
        pieza = {"slide_1_gancho": "a", "slide_2": "b", "slide_3": "c", "slide_4": "Sin cifras.", "slide_5_cierre": "e"}
        doc = pymupdf.open(stream=tarjetas.generar_pdf(pieza, imagenes={3: icono}), filetype="pdf")
        self.assertTrue(doc[2].get_images())          # tarjeta 3: el ícono generado
        self.assertFalse(doc[3].get_images())         # tarjeta 4 (sin cifra): ícono vectorial de la guía

    def test_la_foto_pierde_su_marco_claro(self):
        import io
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (1024, 1024), (232, 232, 230))
        ImageDraw.Draw(im).rectangle([40, 140, 984, 860], fill=(70, 90, 140))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        salida = Image.open(io.BytesIO(tarjetas.recortar(buf.getvalue(), 1080, 620, escala=1, foto=True)))
        for x, y in ((0, 0), (1079, 0), (0, 619), (1079, 619)):
            self.assertEqual(salida.getpixel((x, y))[2] > 120, True, (x, y))   # esquinas = foto, no marco gris

    def test_imagen_se_recorta_al_espacio_de_la_tarjeta(self):
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(tarjetas.recortar(self._foto((0.2, 0.2, 0.8, 0.8)), 1080, 620, escala=1)))
        self.assertEqual(img.size, (1080, 620))

    def test_la_foto_lleva_velo_azul_y_no_dibuja_recuadro(self):
        foto = self._foto((0, 0, 1, 1), fondo=(255, 255, 255))
        doc = pymupdf.open(stream=tarjetas.generar_pdf(carrusel(), guias=True, imagenes={2: foto}), filetype="pdf")
        self.assertTrue(doc[1].get_images())
        self.assertNotIn("FOTO · Krea", doc[1].get_text())
        self.assertIn("ÍCONO ISOMÉTRICO", doc[0].get_text())      # la tarjeta 1 sin imagen conserva su guía
        r, g, b = doc[1].get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2)).pixel(100, 250)[:3]
        self.assertTrue(b > 200 and r < 180, (r, g, b))             # blanco bajo el velo azul → azulado

    def test_nombre_de_archivo(self):
        self.assertEqual(tarjetas.nombre_archivo({"tema_especifico": "Retail media: ¿ya?"}, "2026-11-01"),
                         "tarjetas-2026-11-retail-media-ya.pdf")


if __name__ == "__main__":
    unittest.main()

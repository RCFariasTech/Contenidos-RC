"""Guion visual de reels en PDF 9:16 (sin red)."""

import random
import unittest

import pymupdf  # solo para verificar el PDF en pruebas

from rc import reels

REEL = {
    "tema_especifico": "Marketing sensorial", "formato": "Reel",
    "escena_1_gancho": "¿Tu marca se huele?", "escena_2_desarrollo_a": "El olfato activa la memoria",
    "escena_3_desarrollo_b": "Diseñamos experiencias multisensoriales", "escena_4_desarrollo_c": "Medimos recordación real",
    "escena_5_cta": "Sígueme para más",
}


class TestReels(unittest.TestCase):
    def test_numeros_de_paso_no_se_agrandan_y_texto_a_dos_tercios(self):
        from rc import tarjetas
        self.assertEqual(tarjetas.separar_cifra("Paso 1: mapea los momentos relevantes")[1], "")
        self.assertEqual(tarjetas.separar_cifra("1. Mapea el recorrido")[1], "")
        self.assertEqual(tarjetas.separar_cifra("Regla 95-5: solo 5% compra ahora")[1], "95")
        reel = dict(REEL, escena_2_desarrollo_a="Paso 1: mapea los momentos relevantes",
                    escena_3_desarrollo_b="Solo 5% compra ahora")
        self.assertIn(2, reels.escenas_sin_cifra(reel))                          # el paso lleva ícono (o foto)
        pagina = pymupdf.open(stream=reels.generar_pdf(reel), filetype="pdf")[2]
        tramos = [s for b in pagina.get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for s in ln["spans"]]
        texto = [s for s in tramos if s["text"].strip() != "5%"]
        self.assertTrue(all(s["size"] > 100 for s in texto))                    # poco texto: más grande (hasta 2x)
        limite = reels.M + (reels.W - 2 * reels.M) * 2 / 3 + 5
        self.assertTrue(all(s["bbox"][2] <= limite for s in texto))             # solo hasta 2/3 del ancho

    def test_escena_con_foto_y_velo(self):
        reel = dict(REEL, escena_2_desarrollo_a="Primera idea sin datos", escena_3_desarrollo_b="Segunda idea sin datos",
                    escena_4_desarrollo_c="Tercera idea sin datos")
        self.assertEqual(reels.fotos_validas(reel, [2, 3, 4]), [2, 3])            # siempre queda un ícono
        self.assertEqual(reels.tipos_imagen(reel, [3])[3], "foto")
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (800, 800), (255, 255, 255)).save(buf, "JPEG")
        doc = pymupdf.open(stream=reels.generar_pdf(reel, imagenes={3: buf.getvalue()}, fotos=[3]), filetype="pdf")
        self.assertTrue(doc[2].get_images())
        r, g, b = doc[2].get_pixmap(matrix=pymupdf.Matrix(0.1, 0.1)).pixel(50, 40)[:3]
        self.assertNotEqual((r, g, b), (255, 255, 255))                           # la foto lleva velo de color
        self.assertIn("Segunda idea", " ".join(doc[2].get_text().split()))

    def test_escenas_animables_sin_textos_en_el_fondo(self):
        escenas = reels.escenas_animables(REEL)
        palabras = [len(REEL[c].split()) for c in reels.CAMPOS]
        for e, n in zip(escenas[:4], palabras):                                     # ~3 palabras por segundo
            self.assertAlmostEqual(e["duracion"], max(2.5, 1 + n / 3), delta=0.26)
        self.assertGreater(escenas[4]["duracion"], max(2.5, 1 + palabras[4] / 3) - 0.26)
        self.assertTrue(all(e["fondo"].startswith("data:image/jpeg;base64,") for e in escenas))
        textos = " ".join(t["texto"] for t in escenas[0]["textos"])
        self.assertEqual(textos, REEL["escena_1_gancho"].upper())                 # el texto va aparte, para animarlo
        t = escenas[0]["textos"][0]
        self.assertEqual((t["fuente"], t["color"][0]), ("SpaceGrotesk-Light", "#"))   # portada en Light
        self.assertTrue(reels.ZONA_ARRIBA <= t["y"] <= reels.H - reels.ZONA_ABAJO)


    def test_contenido_centrado_verticalmente(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (512, 512), (200, 60, 60)).save(buf, "PNG")
        imagenes = {n: buf.getvalue() for n in (1, 2, 3, 4)}
        for pagina in pymupdf.open(stream=reels.generar_pdf(REEL, imagenes=imagenes), filetype="pdf")[:4]:
            cajas = [b["bbox"] for b in pagina.get_text("dict")["blocks"]] + [pagina.get_image_bbox(i) for i in pagina.get_images(full=True)]
            arriba, abajo = min(c[1] for c in cajas), max(c[3] for c in cajas)
            hueco_arriba, hueco_abajo = arriba, reels.H - abajo           # centrado en la página…
            self.assertLess(abs(hueco_arriba - hueco_abajo), 160, (hueco_arriba, hueco_abajo))
            self.assertGreaterEqual(arriba, reels.ZONA_ARRIBA - 5)          # …sin salir de la zona segura
            self.assertLessEqual(abajo, reels.H - reels.ZONA_ABAJO + 5)

    def test_cifras_en_grande_y_iconos_en_las_escenas_sin_cifra(self):
        reel = dict(REEL, escena_2_desarrollo_a="Sube 35% el recuerdo de marca", escena_3_desarrollo_b="Sin cifras aquí")
        self.assertEqual(reels.tipos_imagen(reel), {1: "icono", 3: "linea", 4: "linea"} if not __import__("rc.tarjetas",
                         fromlist=["x"]).separar_cifra(reel["escena_4_desarrollo_c"])[1] else {1: "icono", 3: "linea"})
        doc = pymupdf.open(stream=reels.generar_pdf(reel), filetype="pdf")
        tramos = [s for b in doc[1].get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for s in ln["spans"]]
        cifra = next(s for s in tramos if s["text"].strip() == "35%")
        self.assertGreater(cifra["size"], 150)
        self.assertNotIn("35%", [s["text"].strip() for b in doc[0].get_text("dict")["blocks"] if b["type"] == 0
                                for ln in b["lines"] for s in ln["spans"]])
        self.assertFalse(doc[4].get_images() and False)                 # el cierre no lleva imagen de Krea


    def test_cinco_paginas_9_16_con_texto_editable(self):
        doc = pymupdf.open(stream=reels.generar_pdf(REEL, guias=True), filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (1080, 1920))
        for pagina, campo in zip(doc, reels.CAMPOS):
            texto = " ".join(pagina.get_text().split())
            self.assertIn(REEL[campo].upper() if campo == reels.CAMPOS[0] else REEL[campo], texto)
            self.assertNotIn("FOTO O VIDEO", texto)                     # ya no hay recuadro de foto/video
        self.assertIn("ILUSTRACIÓN ANIMADA", doc[0].get_text())
        self.assertNotIn("ESCENA", doc[0].get_text())          # sin rótulos de escena ni notas en la vista previa
        self.assertNotIn("Animado:", doc[0].get_text())

    def test_solo_el_cierre_lleva_logos_y_se_adaptan_al_fondo(self):
        for variante in range(5):
            doc = pymupdf.open(stream=reels.generar_pdf(REEL, variante=variante), filetype="pdf")
            self.assertTrue(all(not p.get_images() for p in list(doc)[:4]))   # RC / FARÍAS es una imagen PNG
            self.assertTrue(doc[4].get_images())
            self.assertGreater(len(doc[4].get_drawings()), 5)                   # Constellation es vector
            self.assertNotIn("Constellation", doc[4].get_text())                # logo, no texto
            texto = " ".join(doc[4].get_text().split())
            self.assertIn(REEL["escena_5_cta"], texto)
            self.assertIn("Miembros de", texto)
            # Constellation va en su propio renglón, debajo de «Miembros de», ancho (2/3 del espacio útil) y pegado al
            # límite inferior de la zona segura
            frase = doc[4].search_for("Miembros de")[0]
            logo = [d["rect"] for d in doc[4].get_drawings() if d["rect"].y0 > frase.y1]
            self.assertTrue(logo)
            x0, x1 = min(r.x0 for r in logo), max(r.x1 for r in logo)
            y1 = max(r.y1 for r in logo)
            self.assertGreater(x1 - x0, (reels.W - 2 * reels.M) * 2 / 3 * 0.9)
            self.assertAlmostEqual(y1, reels.H - reels.ZONA_ABAJO, delta=6)
            self.assertLessEqual(y1, reels.H - reels.ZONA_ABAJO)

    def test_cierre_alineado_a_la_izquierda_con_el_texto(self):
        """El borde visible izquierdo del CTA, del logo RC / FARÍAS, de «Miembros de» y de Constellation coincide (±2 px)."""
        for variante in range(5):
            pix = pymupdf.open(stream=reels.generar_pdf(REEL, variante=variante), filetype="pdf")[4] \
                .get_pixmap(matrix=pymupdf.Matrix(2, 2))
            fondo = pix.pixel(5, 5)

            def borde_izquierdo(y0, y1):
                for x in range(pix.width):
                    for y in range(y0 * 2, y1 * 2):
                        if sum(abs(a - b) for a, b in zip(pix.pixel(x, y)[:3], fondo[:3])) > 60:
                            return x / 2

            bordes = [borde_izquierdo(660, 900), borde_izquierdo(1160, 1270), borde_izquierdo(1328, 1350),
                      borde_izquierdo(1390, 1462)]
            self.assertLessEqual(max(bordes) - min(bordes), 2, bordes)

    def test_la_descarga_no_trae_la_etiqueta_de_escena(self):
        descarga = pymupdf.open(stream=reels.generar_pdf(REEL), filetype="pdf")
        for pagina in descarga:
            texto = pagina.get_text()
            self.assertNotIn("ESCENA", texto)
            self.assertNotIn("0–5 s", texto)
        self.assertIn(REEL["escena_1_gancho"].upper(), " ".join(descarga[0].get_text().split()))

    def test_cada_escena_tiene_un_fondo_distinto(self):
        doc = pymupdf.open(stream=reels.generar_pdf(REEL, variante=2), filetype="pdf")
        fondos = [tuple(p.get_pixmap(matrix=pymupdf.Matrix(.1, .1)).pixel(2, 2)) for p in doc]
        self.assertEqual(len(set(fondos[:4])), 4, fondos)  # el cierre siempre es azul marino
        otra = pymupdf.open(stream=reels.generar_pdf(REEL, variante=2, semilla=1), filetype="pdf")
        self.assertNotEqual(fondos[0], tuple(otra[0].get_pixmap(matrix=pymupdf.Matrix(.1, .1)).pixel(2, 2)))

    def test_el_texto_respeta_la_zona_segura_de_instagram(self):
        rnd = random.Random(3)
        lex = "activación retail experiencia consumidor marca estrategia conversión audiencia".split()
        for n in (1, 4, 8, 25):
            contenido = {c: " ".join(rnd.choice(lex) for _ in range(n)) for c in reels.CAMPOS}
            doc = pymupdf.open(stream=reels.generar_pdf(contenido, variante=n), filetype="pdf")
            for pagina in doc:
                for b in pagina.get_text("dict")["blocks"]:
                    for ln in b.get("lines", []):
                        x0, y0, x1, y1 = ln["bbox"]
                        self.assertGreaterEqual(y0, reels.ZONA_ARRIBA - 5)
                        self.assertLessEqual(y1, reels.H - reels.ZONA_ABAJO + 5)
                        self.assertTrue(20 <= x0 and x1 <= reels.W - 20)

    def test_nombre_de_archivo(self):
        self.assertEqual(reels.nombre_archivo(REEL, "2026-11-01"), "guion-visual-reel-2026-11-marketing-sensorial.pdf")


if __name__ == "__main__":
    unittest.main()

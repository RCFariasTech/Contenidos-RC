"""Tests sin red del planificador y del validador."""

import unittest
from datetime import date, datetime, timezone

from rc import planificador
from rc.config import ajustes
from rc.validador import contar_palabras, validar

CTA = ajustes()["cta"]
HOY = date(2026, 10, 1)
URL = "https://ejemplo.com/estudio"


def carrusel(**cambios):
    pieza = {
        "formato": "Carrusel",
        "tema_especifico": "Retail media en punto de venta",
        "investigacion": {"tendencia": "Retail media in-store", "resumen": "Crece 25% en Latam según un estudio.",
                          "estrategia_clave": "Medir activaciones con datos del retailer",
                          "fuente_titulo": "Estudio", "fuente_url": URL, "fuente_fecha": "2026-05-10"},
        "slide_1_gancho": "Tu góndola ya es un medio",
        "slide_2": "Texto corto.", "slide_3": "Texto corto.", "slide_4": "Texto corto.",
        "slide_5_cierre": "En RC Farias, miembro de Constellation, lo ejecutamos.",
        "caption": f"Un caption atemporal.\n\n{CTA}", "cta": CTA,
        "hashtags": ["#RCFarias", "#BTL", "#Marketing"],
    }
    pieza.update(cambios)
    return pieza


class TestPlanificador(unittest.TestCase):
    def test_mes_siguiente(self):
        self.assertEqual(planificador.mes_siguiente(date(2026, 12, 15)), date(2027, 1, 1))
        self.assertEqual(planificador.mes_siguiente(date(2026, 9, 30)), date(2026, 10, 1))

    def test_hoy_bogota(self):
        # 03:00 UTC del 15 = 22:00 del 14 en Bogotá
        self.assertEqual(planificador.hoy_bogota(datetime(2026, 10, 15, 3, tzinfo=timezone.utc)), date(2026, 10, 14))

    def test_fecha_propuesta_martes(self):
        # Octubre 2026 empieza en jueves: primer martes = 6
        self.assertEqual(planificador.fecha_propuesta(date(2026, 10, 1), 1, "martes"), date(2026, 10, 6))
        self.assertEqual(planificador.fecha_propuesta(date(2026, 10, 1), 4, "martes"), date(2026, 10, 27))

    def test_tipos_por_uso(self):
        tipos = ["A", "B", "C", "D"]
        orden = planificador.ordenar_tipos(tipos, {"A": date(2026, 9, 1), "C": date(2026, 8, 1)})
        self.assertEqual(orden, ["B", "D", "C", "A"])

    def test_planificar_usa_calendario(self):
        a = ajustes()
        slots = planificador.planificar(date(2026, 11, 1), a["calendario"], ["A", "B", "C", "D"], {}, "martes")
        self.assertEqual([s["formato"] for s in slots], ["Carrusel", "Reel", "Carrusel", "Reel"])
        self.assertEqual(len({s["tipo"] for s in slots}), 4)
        self.assertEqual(slots[0]["fecha_publicacion"], date(2026, 11, 3))


class TestValidador(unittest.TestCase):
    def _validar(self, pieza, formato="Carrusel", previas=(), hermanas=(), urls=(URL,)):
        return validar(formato, pieza, list(urls), list(previas), list(hermanas), ajustes(), HOY)

    def test_pieza_valida(self):
        r = self._validar(carrusel())
        self.assertEqual(r["errores"], [])
        self.assertEqual(r["advertencias"], [])

    def test_contar_palabras_ignora_emojis(self):
        self.assertEqual(contar_palabras("📲 Hola mundo — ok"), 3)

    def test_gancho_largo_es_reparable(self):
        r = self._validar(carrusel(slide_1_gancho="uno dos tres cuatro cinco seis siete ocho nueve"))
        self.assertTrue(any("Tarjeta 1" in e for e in r["errores"]))
        self.assertTrue(r["reparables"])

    def test_anio_prohibido(self):
        r = self._validar(carrusel(slide_2="Tendencia clave del 2026"))
        self.assertTrue(any("años" in e for e in r["errores"]))

    def test_cta_y_hashtags(self):
        r = self._validar(carrusel(caption="Sin cta", hashtags=["#Marketing", "#viral"]))
        textos = " ".join(r["errores"])
        self.assertIn("CTA", textos)
        self.assertIn("#RCFarias", textos)
        self.assertIn("prohibidos", textos)
        self.assertIn("exactamente 3", textos)

    def test_cierre_sin_constellation(self):
        r = self._validar(carrusel(slide_5_cierre="Lo hacemos en RC Farias."))
        self.assertTrue(any("Constellation" in e for e in r["errores"]))

    def test_url_inventada_no_reparable(self):
        r = self._validar(carrusel(), urls=["https://otra.com"])
        self.assertTrue(any("búsqueda web" in e for e in r["errores"]))
        self.assertEqual(r["reparables"], [])

    def test_url_compara_sin_query_ni_barra(self):
        r = self._validar(carrusel(), urls=[URL + "/?utm=x"])
        self.assertEqual(r["errores"], [])

    def test_repeticion_de_semilla(self):
        semilla = {"tema_especifico": "Retail media en el punto de venta", "semilla": True}
        r = self._validar(carrusel(), previas=[semilla])
        self.assertTrue(any("repetición" in e for e in r["errores"]))

    def test_tema_distinto_no_es_repeticion(self):
        semilla = {"tema_especifico": "Marketing sensorial", "semilla": True}
        self.assertEqual(self._validar(carrusel(), previas=[semilla])["errores"], [])

    def test_advertencias(self):
        inv = dict(carrusel()["investigacion"], resumen="Sin cifras", fuente_fecha="2023-01-01")
        r = self._validar(carrusel(investigacion=inv))
        self.assertEqual(len(r["advertencias"]), 2)
        self.assertEqual(r["errores"], [])

    def test_fechas_de_fuente_en_espanol(self):
        for texto in ("24 de octubre de 2025", "Octubre de 2025", "2025-10", "sin fecha visible (nota)"):
            inv = dict(carrusel()["investigacion"], fuente_fecha=texto)
            r = self._validar(carrusel(investigacion=inv))
            self.assertFalse(any("formato reconocible" in a for a in r["advertencias"]), texto)

    def test_reel_limites_y_hashtags(self):
        reel = {k: v for k, v in carrusel().items() if not k.startswith("slide_")}
        reel.update(formato="Reel", escena_1_gancho="Tu góndola ya es medio",
                    escena_2_desarrollo_a="uno", escena_3_desarrollo_b="dos", escena_4_desarrollo_c="tres",
                    escena_5_cta="Escríbenos hoy mismo y te contamos cómo", hashtags=["#RCFarias", "#BTL", "#A", "#B", "#C", "#D"])
        r = self._validar(reel, formato="Reel")
        textos = " ".join(r["errores"])
        self.assertIn("Escena 5", textos)
        self.assertIn("entre 3 y 5", textos)


if __name__ == "__main__":
    unittest.main()

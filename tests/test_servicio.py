"""Flujo completo de servicio.py contra una base de datos falsa en memoria (sin red).

La falsa interpreta los mismos filtros PostgREST que usa servicio.py, para detectar
errores de lógica y de filtros sin tocar Supabase ni la API de Anthropic.
"""

import copy
import itertools
import unittest
from datetime import date
from unittest import mock

from rc import db as db_real
from rc import servicio
from rc.config import ajustes

CTA = ajustes()["cta"]
URL = "https://ejemplo.com/estudio"


class BDFalsa:
    ErrorDB = db_real.ErrorDB

    def __init__(self):
        self.tablas = {"meses": [], "piezas": [], "comentarios": [], "versiones_pieza": []}
        self.ids = itertools.count(1)

    @staticmethod
    def _cumple(fila, campo, filtro):
        valor = fila.get(campo)
        op, _, arg = filtro.partition(".")
        if op == "eq":
            return str(valor) == arg
        if op == "lt":
            return str(valor) < arg
        if op == "in":
            return str(valor) in arg.strip("()").split(",")
        if op == "is":
            return valor is None
        if op == "not":
            op2, _, arg2 = arg.partition(".")
            if op2 == "is":
                return valor is not None
            if op2 == "in":
                return str(valor) not in arg2.strip("()").split(",")
        raise AssertionError(f"filtro no soportado: {campo}={filtro}")

    def _filtrar(self, tabla, filtros):
        especiales = {"select", "order", "limit"}
        return [f for f in self.tablas[tabla]
                if all(self._cumple(f, c, v) for c, v in filtros.items() if c not in especiales)]

    def _con_embebidos(self, tabla, fila, select):
        fila = copy.deepcopy(fila)
        if tabla == "piezas" and "meses(" in select:
            fila["meses"] = next(m for m in self.tablas["meses"] if m["id"] == fila["mes_id"])
        if tabla == "piezas" and "comentarios(" in select:
            fila["comentarios"] = [c for c in self.tablas["comentarios"] if c["pieza_id"] == fila["id"]]
        return fila

    def seleccionar(self, tabla, **params):
        filas = self._filtrar(tabla, params)
        if params.get("order") == "semana":
            filas = sorted(filas, key=lambda f: f["semana"])
        return [self._con_embebidos(tabla, f, params.get("select", "*")) for f in filas]

    def insertar(self, tabla, filas):
        nuevas = []
        for f in (filas if isinstance(filas, list) else [filas]):
            if tabla == "meses" and any(m["mes_objetivo"] == f["mes_objetivo"] for m in self.tablas["meses"]):
                raise db_real.ErrorDB(409, "duplicado")
            fila = {"id": next(self.ids), **f}
            if tabla == "piezas":
                fila = {"estado": "pendiente", "version": 0, "contenido": None, "validacion": None,
                        "uso_tokens": None, "error_msg": None, "aprobada_en": None,
                        "actualizado_en": "2099-01-01T00:00:00+00:00", **fila}
            if tabla == "meses":
                fila.setdefault("estado", "generando")
            if tabla == "comentarios":
                fila = {"aplicado_en": None, "version_resultante": None, **fila}
            self.tablas[tabla].append(fila)
            nuevas.append(copy.deepcopy(fila))
        return nuevas

    def actualizar(self, tabla, cambios, **filtros):
        filas = self._filtrar(tabla, filtros)
        for f in filas:
            f.update(copy.deepcopy(cambios))
        return copy.deepcopy(filas)

    def borrar(self, tabla, **filtros):
        filas = self._filtrar(tabla, filtros)
        self.tablas[tabla] = [f for f in self.tablas[tabla] if f not in filas]
        return filas


def pieza_generada(formato, tema):
    base = {
        "formato": formato, "tema_especifico": tema,
        "investigacion": {"tendencia": f"Tendencia {tema}", "resumen": "Crece 25% según estudio.",
                          "estrategia_clave": f"Estrategia {tema}", "fuente_titulo": "Estudio",
                          "fuente_url": URL, "fuente_fecha": "2026-06-01"},
        "caption": f"Caption atemporal.\n\n{CTA}", "cta": CTA, "hashtags": ["#RCFarias", "#BTL", "#Marketing"],
    }
    if formato == "Carrusel":
        base.update(slide_1_gancho="Gancho corto", slide_2="a", slide_3="b", slide_4="c",
                    slide_5_cierre="Desde RC Farias, miembro de Constellation.")
    else:
        base.update(escena_1_gancho="Gancho corto", escena_2_desarrollo_a="a", escena_3_desarrollo_b="b",
                    escena_4_desarrollo_c="c", escena_5_cta="Síguenos ya")
    return base


class TestFlujo(unittest.TestCase):
    def setUp(self):
        self.bd = BDFalsa()
        temas = iter(["Retail media", "Comercio conversacional", "Experiencias olfativas", "Eventos híbridos",
                      "Gancho ajustado"])

        def generar(slot, historial, hermanas):
            return {"pieza": pieza_generada(slot["formato"], next(temas)), "urls": [URL],
                    "uso": {"input_tokens": 100, "output_tokens": 50}}

        def ajustar(slot, pieza, comentarios, historial, hermanas):
            nueva = dict(pieza, slide_1_gancho="Nuevo gancho directo") if slot["formato"] == "Carrusel" else dict(pieza)
            return {"pieza": nueva, "urls": [], "uso": {"input_tokens": 10, "output_tokens": 5}}

        parches = [mock.patch.object(servicio, "db", self.bd),
                   mock.patch.object(servicio.generador, "generar", side_effect=generar),
                   mock.patch.object(servicio.generador, "ajustar", side_effect=ajustar)]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)

    def test_flujo_completo(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        servicio.iniciar_mes(mes)  # idempotente
        estado = servicio.estado_mes(mes)
        self.assertEqual(len(estado["piezas"]), 4)
        self.assertEqual([p["estado"] for p in estado["piezas"]], ["pendiente"] * 4)

        for p in estado["piezas"]:
            fila = servicio.generar_pieza(p["id"])
            self.assertEqual(fila["estado"], "generada", fila.get("validacion"))
            self.assertEqual(fila["validacion"]["errores"], [])
        estado = servicio.estado_mes(mes)
        self.assertEqual(estado["mes"]["estado"], "en_revision")
        self.assertNotIn("urls", estado["piezas"][0]["validacion"])

        primera = estado["piezas"][0]["id"]
        servicio.comentar(primera, "Haz el gancho más directo")
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.aprobar(primera, True)  # comentario pendiente
        ajustada = servicio.ajustar_pieza(primera)
        self.assertEqual(ajustada["version"], 2)
        self.assertEqual(ajustada["contenido"]["slide_1_gancho"], "Nuevo gancho directo")
        comentario = servicio.estado_mes(mes)["piezas"][0]["comentarios"][0]
        self.assertEqual(comentario["version_resultante"], 2)
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.borrar_comentario(comentario["id"])  # ya aplicado

        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.aprobar(p["id"], True)
        self.assertEqual(servicio.estado_mes(mes)["mes"]["estado"], "aprobado")

        servicio.aprobar(primera, False)
        estado = servicio.estado_mes(mes)
        self.assertEqual(estado["mes"]["estado"], "en_revision")
        self.assertEqual(estado["piezas"][0]["estado"], "generada")

    def test_exportar_marca_entregado(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.exportar_pptx(mes)  # aún no aprobado
        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.generar_pieza(p["id"])
            servicio.aprobar(p["id"], True)
        nombre, contenido = servicio.exportar_pptx(mes)
        self.assertEqual(nombre, "RC_Farias_Instagram_2026-11.pptx")
        self.assertTrue(contenido.startswith(b"PK"))
        fila = servicio.estado_mes(mes)["mes"]
        self.assertEqual(fila["estado"], "entregado")
        self.assertIsNotNone(fila["entregado_en"])
        servicio.exportar_pptx(mes)  # se puede volver a descargar

    def test_fecha_y_comentarios(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        pieza = servicio.estado_mes(mes)["piezas"][0]
        self.assertEqual(pieza["fecha_publicacion"], "2026-11-03")
        self.assertEqual(servicio.cambiar_fecha(pieza["id"], "2026-11-05")["fecha_publicacion"], "2026-11-05")
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.cambiar_fecha(pieza["id"], "05/11/2026")
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.comentar(pieza["id"], "antes de generar")
        servicio.generar_pieza(pieza["id"])
        c = servicio.comentar(pieza["id"], "  algo  ")
        self.assertEqual(c["texto"], "algo")
        servicio.borrar_comentario(c["id"])
        self.assertEqual(servicio.estado_mes(mes)["piezas"][0]["comentarios"], [])

    def test_fallo_de_generacion_deja_error(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        pieza = servicio.estado_mes(mes)["piezas"][0]
        with mock.patch.object(servicio.generador, "generar", side_effect=RuntimeError("API caída")):
            with self.assertRaises(RuntimeError):
                servicio.generar_pieza(pieza["id"])
        fila = servicio.estado_mes(mes)["piezas"][0]
        self.assertEqual(fila["estado"], "error")
        self.assertIn("API caída", fila["error_msg"])
        self.assertEqual(servicio.generar_pieza(pieza["id"])["estado"], "generada")  # reintento


if __name__ == "__main__":
    unittest.main()

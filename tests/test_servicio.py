"""Flujo completo de servicio.py contra una base de datos falsa en memoria (sin red).

La falsa interpreta los mismos filtros PostgREST que usa servicio.py, para detectar
errores de lógica y de filtros sin tocar Supabase ni la API de Anthropic.
"""

import copy
import itertools
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from rc import correos, fuentes, krea, teams
from rc import db as db_real
from rc import servicio
from rc.config import ajustes
from tests.test_logica import diseno_de

CTA = ajustes()["cta"]
URL = "https://www.warc.com/estudio"


class BDFalsa:
    ErrorDB = db_real.ErrorDB

    def __init__(self):
        self.tablas = {"meses": [], "piezas": [], "comentarios": [], "versiones_pieza": [],
                       "fuentes_confiables": [], "correos_favoritos": [], "ilustraciones": []}
        self.unicos = {"fuentes_confiables": "dominio", "correos_favoritos": "email", "meses": "mes_objetivo"}
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
            return valor is {"null": None, "true": True, "false": False}[arg]
        if op == "not":
            op2, _, arg2 = arg.partition(".")
            if op2 == "is":
                return valor is not None
            if op2 == "in":
                return str(valor) not in arg2.strip("()").split(",")
        raise AssertionError(f"filtro no soportado: {campo}={filtro}")

    def _filtrar(self, tabla, filtros):
        especiales = {"select", "order", "limit"}
        if tabla == "piezas" and "mes_id" not in {"x"}:
            pass

        def valor_fila(fila, campo):
            if campo.startswith("meses."):  # filtro sobre la tabla embebida (meses!inner)
                mes = next(m for m in self.tablas["meses"] if m["id"] == fila["mes_id"])
                return {campo: mes[campo.split(".", 1)[1]]}
            return fila

        return [f for f in self.tablas[tabla]
                if all(self._cumple(valor_fila(f, c), c, v) for c, v in filtros.items() if c not in especiales)]

    def _con_embebidos(self, tabla, fila, select):
        fila = copy.deepcopy(fila)
        if tabla == "piezas" and ("meses(" in select or "meses!inner(" in select):
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
            clave = self.unicos.get(tabla)
            if clave and any(x[clave] == f[clave] for x in self.tablas[tabla]):
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
            if tabla == "ilustraciones":
                fila = {"estado": "en_cola", "url": None, "error": None, "elegida": False, "descripcion": None,
                        "creado_en": datetime.now(timezone.utc).isoformat(), **fila}
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
        if tabla == "piezas":  # on delete cascade
            ids = {f["id"] for f in filas}
            for t in ("comentarios", "versiones_pieza", "ilustraciones"):
                self.tablas[t] = [f for f in self.tablas[t] if f["pieza_id"] not in ids]
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
                    slide_5_cierre="Desde RC Farías, miembro de Constellation.")
        base["diseno"] = diseno_de(base)
    else:
        base.update(escena_1_gancho="Gancho corto", escena_2_desarrollo_a="a", escena_3_desarrollo_b="b",
                    escena_4_desarrollo_c="c", escena_5_cta="Síguenos ya")
    return base


class TestFlujo(unittest.TestCase):
    def setUp(self):
        self.bd = BDFalsa()
        temas = iter(["Retail media", "Comercio conversacional", "Experiencias olfativas", "Eventos híbridos",
                      "Gancho ajustado"])

        def generar(slot, historial, hermanas, descartados=None):
            return {"pieza": pieza_generada(slot["formato"], next(temas)), "urls": [URL],
                    "uso": {"input_tokens": 100, "output_tokens": 50}}

        def ajustar(slot, pieza, comentarios, historial, hermanas):
            nueva = dict(pieza, slide_1_gancho="Nuevo gancho directo") if slot["formato"] == "Carrusel" else dict(pieza)
            if slot["formato"] == "Carrusel":
                nueva["diseno"] = diseno_de(nueva)
            return {"pieza": nueva, "urls": [], "uso": {"input_tokens": 10, "output_tokens": 5}}

        parches = [mock.patch.object(servicio, "db", self.bd), mock.patch.object(fuentes, "db", self.bd),
                   mock.patch.object(correos, "db", self.bd),
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

        carruseles = [p for p in estado["piezas"] if p["formato"] == "Carrusel"]
        for c in carruseles:
            nombre, pdf = servicio.tarjetas_pdf(c["id"])
            self.assertTrue(nombre.startswith("tarjetas-2026-11-") and pdf.startswith(b"%PDF"))
            vista = servicio.vista_tarjetas(c["id"])
            self.assertEqual((len(vista["imagenes"]), vista["relacion"]), (5, 0.75))
            self.assertTrue(all(i.startswith("data:image/png;base64,") for i in vista["imagenes"]))
        reel = next(p for p in estado["piezas"] if p["formato"] == "Reel")
        nombre, pdf = servicio.tarjetas_pdf(reel["id"])
        self.assertTrue(nombre.startswith("guion-visual-reel-2026-11-") and pdf.startswith(b"%PDF"))
        self.assertAlmostEqual(servicio.vista_tarjetas(reel["id"])["relacion"], 9 / 16)

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

    def test_repositorio_y_versiones(self):
        historico = self.bd.insertar("meses", {"mes_objetivo": "2000-01-01", "estado": "historico"})[0]
        self.bd.insertar("piezas", {"mes_id": historico["id"], "semana": 1, "formato": "Carrusel", "tipo": "Histórico",
                                    "pilar": "Histórico", "estado": "aprobada", "version": 1,
                                    "contenido": {"tema_especifico": "Cringe marketing", "semilla": True}})
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        self.assertEqual([r["tema"] for r in servicio.repositorio()], ["Cringe marketing"])  # mes sin aprobar no aparece
        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.generar_pieza(p["id"])
            servicio.aprobar(p["id"], True)
        repo = servicio.repositorio()
        self.assertEqual(len(repo), 5)
        self.assertEqual(repo[0]["mes_objetivo"], "2026-11-01")
        self.assertEqual(repo[0]["semana"], 4)  # más recientes primero
        self.assertTrue(repo[-1]["historico"])
        self.assertIsNone(repo[-1]["mes_objetivo"])
        primera = servicio.estado_mes(mes)["piezas"][0]["id"]
        self.assertEqual([v["version"] for v in servicio.versiones(primera)], [1])

    def _mes_aprobado(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.generar_pieza(p["id"])
            servicio.aprobar(p["id"], True)
        return mes

    def test_fuentes_agregar_quitar_y_respaldo(self):
        self.assertEqual(fuentes.dominios(), fuentes.recomendadas())  # tabla vacía → lista recomendada
        self.assertEqual(fuentes.agregar("https://www.Kantar.com/informe"), "kantar.com")
        self.assertEqual(fuentes.agregar("warc.com"), "warc.com")
        with self.assertRaises(servicio.ErrorNegocio):
            fuentes.agregar("kantar.com")  # duplicada
        for malo in ("", "no es un dominio", "localhost", "a.b"):
            with self.assertRaises(servicio.ErrorNegocio):
                fuentes.agregar(malo)
        self.assertEqual(fuentes.dominios(), ["kantar.com", "warc.com"])
        fuentes.quitar("kantar.com")
        with self.assertRaises(servicio.ErrorNegocio):
            fuentes.quitar("warc.com")  # no se puede quedar sin fuentes
        self.assertEqual(fuentes.restaurar(), len(fuentes.recomendadas()) - 1)
        self.assertIn("warc.com", fuentes.listar())

    def test_favoritos(self):
        f = correos.agregar_favorito(" Luis@RCFarias.com ", "Luis Alfonso")
        self.assertEqual(f["email"], "luis@rcfarias.com")
        with self.assertRaises(servicio.ErrorNegocio):
            correos.agregar_favorito("luis@rcfarias.com")
        with self.assertRaises(servicio.ErrorNegocio):
            correos.agregar_favorito("sin-arroba")
        self.assertEqual(correos.separar_correos("a@x.co, b@y.com;  c@z.org"), ["a@x.co", "b@y.com", "c@z.org"])
        correos.borrar_favorito(f["id"])
        self.assertEqual(correos.listar_favoritos(), [])

    def test_enviar_pptx(self):
        mes = self._mes_aprobado()
        enviados = []
        with mock.patch.object(correos, "enviar", side_effect=lambda *a: enviados.append(a)):
            r = servicio.enviar_pptx(mes, ["Luis@rcfarias.com", "luis@rcfarias.com", "otro@x.co"], "Para publicar",
                                     guardar_favoritos=True)
        self.assertEqual(r, ["luis@rcfarias.com", "otro@x.co"])
        destinatarios, asunto, cuerpo, adjunto, nombre = enviados[0]
        self.assertIn("Noviembre 2026", asunto)
        self.assertIn("Para publicar", cuerpo)
        self.assertTrue(adjunto.startswith(b"PK"))
        self.assertEqual(nombre, "RC_Farias_Instagram_2026-11.pptx")
        self.assertEqual(servicio.estado_mes(mes)["mes"]["estado"], "entregado")
        self.assertEqual([f["email"] for f in correos.listar_favoritos()], ["luis@rcfarias.com", "otro@x.co"])

    def test_enviar_fallido_no_marca_entregado(self):
        mes = self._mes_aprobado()
        with mock.patch.object(correos, "enviar", side_effect=servicio.ErrorNegocio("SMTP caído")):
            with self.assertRaises(servicio.ErrorNegocio):
                servicio.enviar_pptx(mes, ["a@x.co"])
        self.assertEqual(servicio.estado_mes(mes)["mes"]["estado"], "aprobado")

    def test_rehacer_propuesta_busca_otro_tema(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.generar_pieza(p["id"])
        pieza = servicio.estado_mes(mes)["piezas"][1]
        tema_viejo = pieza["contenido"]["tema_especifico"]
        recibido = {}

        def nueva(slot, historial, hermanas, descartados=None):
            recibido["descartados"] = descartados
            recibido["hermanas"] = hermanas
            return {"pieza": pieza_generada(slot["formato"], "Gamificación en activaciones de marca"), "urls": [URL],
                    "uso": {"input_tokens": 10, "output_tokens": 5}}

        servicio.comentar(pieza["id"], "ajusta algo")
        with self.assertRaises(servicio.ErrorNegocio):  # comentario pendiente
            servicio.rehacer_pieza(pieza["id"])
        servicio.borrar_comentario(servicio.estado_mes(mes)["piezas"][1]["comentarios"][0]["id"])

        with mock.patch.object(servicio.generador, "generar", side_effect=nueva):
            fila = servicio.rehacer_pieza(pieza["id"])
        self.assertEqual((fila["version"], fila["estado"]), (2, "generada"))
        self.assertEqual(fila["contenido"]["tema_especifico"], "Gamificación en activaciones de marca")
        self.assertEqual([d["contenido"]["tema_especifico"] for d in recibido["descartados"]], [tema_viejo])
        self.assertIn(tema_viejo, [h["contenido"]["tema_especifico"] for h in recibido["hermanas"]])
        self.assertEqual({v["motivo"] for v in servicio.versiones(pieza["id"])}, {"rehacer", "generacion"})

        servicio.aprobar(pieza["id"], True)
        with self.assertRaises(servicio.ErrorNegocio):  # aprobada: no se rehace
            servicio.rehacer_pieza(pieza["id"])

    def test_rehacer_que_falla_conserva_la_propuesta_anterior(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.generar_pieza(p["id"])
        pieza = servicio.estado_mes(mes)["piezas"][0]
        with mock.patch.object(servicio.generador, "generar", side_effect=RuntimeError("API caída")):
            with self.assertRaises(RuntimeError):
                servicio.rehacer_pieza(pieza["id"])
        despues = servicio.estado_mes(mes)["piezas"][0]
        self.assertEqual((despues["estado"], despues["version"]), ("generada", 1))
        self.assertEqual(despues["contenido"], pieza["contenido"])
        self.assertIn("No se pudo rehacer", despues["error_msg"])

    def _mes_generado(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        for p in servicio.estado_mes(mes)["piezas"]:
            servicio.generar_pieza(p["id"])
        piezas = servicio.estado_mes(mes)["piezas"]
        return (next(p for p in piezas if p["formato"] == "Carrusel"), next(p for p in piezas if p["formato"] == "Reel"))

    def test_generar_ilustraciones_pide_varias_variantes_a_krea(self):
        carrusel, reel = self._mes_generado()
        trabajos = iter(f"job-{i}" for i in range(1, 20))
        enviados = []

        def crear(prompt, ancho, alto):
            enviados.append((prompt, ancho, alto))
            return next(trabajos)

        with mock.patch.object(krea, "configurado", return_value=True), \
                mock.patch.object(krea, "crear_trabajo", side_effect=crear):
            filas = servicio.generar_ilustraciones(carrusel["id"], 1)["items"]
            self.assertEqual(len(filas), 3)
            self.assertEqual({f["job_id"] for f in filas}, {"job-1", "job-2", "job-3"})
            self.assertEqual({f["estado"] for f in filas}, {"en_cola"})
            prompt, ancho, alto = enviados[0]
            self.assertIn("3d of a 3D character pushing a shopping cart", prompt)  # el prompt_krea de la tarjeta
            self.assertRegex(prompt, r", isolated in a [a-z ]+ background$")       # fondo de la tarjeta, al estilo RC
            self.assertEqual((ancho, alto), (1216, 848))                        # recuadro de la portada
            self.assertEqual(filas[0]["fondo"][0], "#")
            self.assertEqual(len(servicio.generar_ilustraciones(carrusel["id"], 2)["items"]), 3)
            for caso in ((carrusel["id"], 3), (reel["id"], 1)):
                with self.assertRaises(servicio.ErrorNegocio):
                    servicio.generar_ilustraciones(*caso)
        with mock.patch.object(krea, "configurado", return_value=False):
            with self.assertRaises(servicio.ErrorNegocio) as ctx:
                servicio.generar_ilustraciones(carrusel["id"], 1)
        self.assertIn("KREA_API_TOKEN", str(ctx.exception))

    def test_cada_ilustracion_se_describe_con_el_texto_de_su_tarjeta(self):
        carrusel, _ = self._mes_generado()
        pieza = servicio._pieza(carrusel["id"])
        for d in pieza["contenido"]["diseno"]:
            d["prompt_krea"] = ""          # como un carrusel generado antes de existir prompt_krea
        self.bd.tablas["piezas"][[p["id"] for p in self.bd.tablas["piezas"]].index(carrusel["id"])]["contenido"] = pieza["contenido"]
        pedidas, enviados = [], []

        def describir(tema, titular, texto, nota=""):
            pedidas.append((titular, texto))
            return f"3d of a scene for {titular}"

        with mock.patch.object(krea, "configurado", return_value=True), \
                mock.patch.object(krea, "crear_trabajo", side_effect=lambda p, a, h: enviados.append(p) or f"j{len(enviados)}"), \
                mock.patch.object(servicio.generador, "describir_ilustracion", side_effect=describir):
            r2 = servicio.generar_ilustraciones(carrusel["id"], 2)
            r_user = servicio.generar_ilustraciones(carrusel["id"], 1, descripcion="Two 3D robots shaking hands")
        t2 = servicio._texto_tarjeta(pieza["contenido"], 2)
        self.assertEqual(pedidas, [(t2["titular"], t2["texto"])])            # Claude recibe el texto de la tarjeta 2
        self.assertEqual(r2["descripcion"], f"3d of a scene for {t2['titular']}")
        self.assertIn(f"3d of a scene for {t2['titular']}", enviados[0])
        self.assertEqual(r_user["descripcion"], "Two 3D robots shaking hands")  # la del usuario manda y no llama a Claude
        self.assertTrue(all(f["descripcion"] == "Two 3D robots shaking hands" for f in r_user["items"]))

    def test_elegir_una_ilustracion_por_tarjeta_y_montarla_en_el_pdf(self):
        import pymupdf
        from rc import tarjetas
        carrusel, _ = self._mes_generado()
        with mock.patch.object(krea, "configurado", return_value=True), \
                mock.patch.object(krea, "crear_trabajo", side_effect=["a", "b", "c"]):
            filas = servicio.generar_ilustraciones(carrusel["id"], 1)["items"]
        with self.assertRaises(servicio.ErrorNegocio):           # aún en cola: no se puede usar
            servicio.elegir_ilustracion(filas[0]["id"])
        for f in self.bd.tablas["ilustraciones"]:
            f.update(estado="lista", url=f"https://gen.krea.ai/images/{f['job_id']}.png")
        servicio.elegir_ilustracion(filas[0]["id"])
        servicio.elegir_ilustracion(filas[1]["id"])
        elegidas = [f["job_id"] for f in self.bd.tablas["ilustraciones"] if f["elegida"]]
        self.assertEqual(elegidas, ["b"])                         # solo una por tarjeta
        png = tarjetas.imagenes_png(tarjetas.generar_pdf({"slide_1_gancho": "x"}), 400)[0]

        class Resp:
            def __init__(self, datos): self.datos = datos
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return self.datos

        with mock.patch("urllib.request.urlopen", lambda req, timeout=None: Resp(png)):
            _, pdf = servicio.tarjetas_pdf(carrusel["id"])
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        self.assertTrue(doc[0].get_images())                      # tarjeta 1 con la ilustración montada
        self.assertNotIn("ILUSTRACIÓN 3D", doc[0].get_text())
        servicio.elegir_ilustracion(filas[1]["id"], False)        # quitarla
        self.assertFalse(any(f["elegida"] for f in self.bd.tablas["ilustraciones"]))

    def test_ilustraciones_falla_a_medias_conserva_las_que_si_salieron(self):
        carrusel, _ = self._mes_generado()
        respuestas = [lambda: "job-a", lambda: (_ for _ in ()).throw(servicio.ErrorNegocio("Krea tiene demasiados trabajos"))]
        with mock.patch.object(krea, "configurado", return_value=True), \
                mock.patch.object(krea, "crear_trabajo", side_effect=lambda *a: respuestas.pop(0)()):
            filas = servicio.generar_ilustraciones(carrusel["id"], 1)["items"]
        self.assertEqual([f["job_id"] for f in filas], ["job-a"])

    def test_ilustraciones_consulta_y_actualiza_el_estado(self):
        carrusel, _ = self._mes_generado()
        with mock.patch.object(krea, "configurado", return_value=True), \
                mock.patch.object(krea, "crear_trabajo", side_effect=["j1", "j2", "j3"]):
            servicio.generar_ilustraciones(carrusel["id"], 1)
        estados = {"j1": {"estado": "lista", "url": "https://gen.krea.ai/images/x.png", "error": None},
                   "j2": {"estado": "en_cola", "url": None, "error": None},
                   "j3": {"estado": "fallida", "url": None, "error": "Krea no pudo generarla."}}
        with mock.patch.object(krea, "configurado", return_value=True), \
                mock.patch.object(krea, "consultar", side_effect=lambda j: estados[j]):
            res = servicio.ilustraciones(carrusel["id"])
        por_job = {f["job_id"]: f for f in res["items"]}
        self.assertEqual(por_job["j1"]["url"], "https://gen.krea.ai/images/x.png")
        self.assertEqual((por_job["j1"]["estado"], por_job["j2"]["estado"], por_job["j3"]["estado"]),
                         ("lista", "en_cola", "fallida"))
        # un trabajo en cola desde hace demasiado tiempo se da por fallido
        for f in self.bd.tablas["ilustraciones"]:
            f["creado_en"] = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        with mock.patch.object(krea, "consultar", side_effect=lambda j: estados[j]):
            res = servicio.ilustraciones(carrusel["id"])
        self.assertEqual({f["job_id"]: f["estado"] for f in res["items"]}["j2"], "fallida")

    def test_teams_avisa_una_sola_vez_cuando_el_mes_queda_en_revision(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        ids = [p["id"] for p in servicio.estado_mes(mes)["piezas"]]
        with mock.patch.dict("os.environ", {"TEAMS_WEBHOOK_URL": "https://example.webhook.office.com/x"}), \
                mock.patch.object(teams, "_publicar") as publicar:
            for i in ids[:3]:
                servicio.generar_pieza(i)
            publicar.assert_not_called()  # faltan piezas
            servicio.generar_pieza(ids[3])
            publicar.assert_called_once()
            tarjeta = publicar.call_args.args[0]["attachments"][0]["content"]
            self.assertIn("Noviembre 2026", tarjeta["body"][0]["text"])
            self.assertEqual(tarjeta["actions"][0]["url"], teams.APP_URL_POR_DEFECTO)
            servicio.comentar(ids[0], "ajusta")
            servicio.ajustar_pieza(ids[0])  # ajustar no vuelve a avisar
            publicar.assert_called_once()

    def test_teams_caido_no_rompe_la_generacion(self):
        mes = date(2026, 11, 1)
        servicio.iniciar_mes(mes)
        with mock.patch.dict("os.environ", {"TEAMS_WEBHOOK_URL": "https://example.webhook.office.com/x"}), \
                mock.patch.object(teams, "_publicar", side_effect=servicio.ErrorNegocio("Teams caído")):
            for p in servicio.estado_mes(mes)["piezas"]:
                servicio.generar_pieza(p["id"])
        self.assertEqual(servicio.estado_mes(mes)["mes"]["estado"], "en_revision")

    def test_teams_sin_configurar_no_hace_nada(self):
        with mock.patch.dict("os.environ", {"TEAMS_WEBHOOK_URL": ""}):
            self.assertFalse(teams.avisar_revision("2026-11-01", 4))
            with self.assertRaises(servicio.ErrorNegocio):
                teams.enviar_prueba()

    def test_smtp_no_configurado(self):
        with mock.patch.dict("os.environ", {"SMTP_USER": "", "SMTP_PASSWORD": ""}):
            with self.assertRaises(servicio.ErrorNegocio) as ctx:
                correos.enviar(["a@x.co"], "a", "b", b"x", "f.pptx")
        self.assertIn("SMTP_USER", str(ctx.exception))

    def test_borrar_piezas_del_repositorio(self):
        mes = self._mes_aprobado()
        ids = [p["id"] for p in servicio.estado_mes(mes)["piezas"]]
        servicio.comentar  # (los comentarios/versiones se borran en cascada)
        self.assertEqual(servicio.borrar_piezas(ids[:2]), 2)
        self.assertEqual(len(servicio.estado_mes(mes)["piezas"]), 2)
        self.assertEqual(len([v for v in self.bd.tablas["versiones_pieza"] if v["pieza_id"] in ids[:2]]), 0)
        servicio.borrar_piezas(ids[2:])
        self.assertIsNone(servicio.obtener_mes(mes))  # mes vacío → se borra
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.borrar_piezas([])

    def test_no_se_borra_un_mes_en_revision(self):
        mes = date(2026, 12, 1)
        servicio.iniciar_mes(mes)
        pieza = servicio.estado_mes(mes)["piezas"][0]["id"]
        servicio.generar_pieza(pieza)
        with self.assertRaises(servicio.ErrorNegocio):
            servicio.borrar_piezas([pieza])

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

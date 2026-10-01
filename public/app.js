"use strict";

// ---------- sesión y API ----------

// Tokens de Supabase Auth en localStorage (con try/catch: puede no estar disponible).
const Sesion = {
  leer() { try { return JSON.parse(localStorage.getItem("rc_sesion") || "null"); } catch { return null; } },
  guardar(s) { try { localStorage.setItem("rc_sesion", JSON.stringify(s)); } catch { /* sin almacenamiento */ } },
  borrar() { try { localStorage.removeItem("rc_sesion"); } catch { /* sin almacenamiento */ } },
};

let config = null;

async function cargarConfig() {
  const r = await fetch("/api/config");
  if (!r.ok) throw new Error("No se pudo cargar la configuración");
  config = await r.json();
}

async function authSupabase(grantType, cuerpo) {
  const r = await fetch(`${config.supabase_url}/auth/v1/token?grant_type=${grantType}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: config.supabase_anon_key },
    body: JSON.stringify(cuerpo),
  });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.error_description || datos.msg || "Credenciales inválidas");
  Sesion.guardar({ access_token: datos.access_token, refresh_token: datos.refresh_token });
}

async function api(ruta, { metodo = "GET", cuerpo } = {}, reintentar = true) {
  const sesion = Sesion.leer();
  const opciones = {
    method: metodo,
    headers: { Authorization: `Bearer ${sesion?.access_token || ""}` },
  };
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  const r = await fetch(`/api/${ruta}`, opciones);
  if (r.status === 401 && reintentar && sesion?.refresh_token) {
    try {
      await authSupabase("refresh_token", { refresh_token: sesion.refresh_token });
      return api(ruta, { metodo, cuerpo }, false);
    } catch { Sesion.borrar(); }
  }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    const error = new Error(datos.error || `Error ${r.status}`);
    error.estado = r.status;
    throw error;
  }
  return datos;
}

// ---------- utilidades de DOM (solo textContent: el contenido generado no es confiable) ----------

function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (clave === "clase") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else if (valor === true) nodo.setAttribute(clave, "");
    else nodo.setAttribute(clave, valor);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

const $ = (id) => document.getElementById(id);

function contarPalabras(texto) {
  return (texto || "").split(/\s+/).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "septiembre", "octubre", "noviembre", "diciembre"];

function nombreMes(iso) {
  const [anio, mes] = iso.split("-").map(Number);
  return `${MESES[mes - 1][0].toUpperCase()}${MESES[mes - 1].slice(1)} ${anio}`;
}

const CAMPOS = {
  Carrusel: [
    { campo: "slide_1_gancho", rol: "Gancho", max: 8 },
    { campo: "slide_2", rol: "Contenido", max: 30 },
    { campo: "slide_3", rol: "Contenido", max: 30 },
    { campo: "slide_4", rol: "Contenido", max: 30 },
    { campo: "slide_5_cierre", rol: "Cierre", max: 30 },
  ],
  Reel: [
    { campo: "escena_1_gancho", rol: "Gancho · 0-5 s", max: 6 },
    { campo: "escena_2_desarrollo_a", rol: "Desarrollo · 5-12 s", max: 8 },
    { campo: "escena_3_desarrollo_b", rol: "Desarrollo · 12-20 s", max: 8 },
    { campo: "escena_4_desarrollo_c", rol: "Desarrollo · 20-25 s", max: 8 },
    { campo: "escena_5_cta", rol: "CTA · 25-30 s", max: 6 },
  ],
};

const ESTADOS_MES = {
  generando: "Generando propuestas", en_revision: "En revisión", aprobado: "Aprobado",
  entregado: "Entregado", historico: "Histórico",
};

// ---------- estado de la vista ----------

const estado = { mes: null, piezas: [], ocupadas: new Set(), mensajes: {}, borradores: {}, generandoTodo: false };

function pendientes(pieza) {
  return (pieza.comentarios || []).filter((c) => !c.aplicado_en);
}

function aviso(texto) {
  const nodo = $("aviso-global");
  nodo.textContent = texto || "";
  nodo.hidden = !texto;
}

// ---------- render ----------

function renderBarra() {
  const { mes, piezas } = estado;
  const mesIso = estado.mesObjetivo;
  $("titulo-mes").textContent = `Propuestas · ${nombreMes(mesIso)}`;
  const aprobadas = piezas.filter((p) => p.estado === "aprobada").length;
  $("resumen-mes").textContent = mes
    ? `${ESTADOS_MES[mes.estado] || mes.estado} · ${aprobadas} de ${piezas.length} piezas aprobadas`
    : "Aún no hay propuestas para este mes.";
  $("btn-generar").hidden = Boolean(mes);
  const conComentarios = piezas.filter((p) => pendientes(p).length && p.estado === "generada").length;
  const botonAjustes = $("btn-ajustes");
  botonAjustes.textContent = conComentarios ? `Aplicar ajustes (${conComentarios})` : "Aplicar ajustes";
  botonAjustes.disabled = !conComentarios || estado.ocupadas.size > 0;
  const listo = mes && ["aprobado", "entregado"].includes(mes.estado);
  const botonPptx = $("btn-pptx");
  botonPptx.disabled = !listo;
  botonPptx.classList.toggle("btn--primario", Boolean(listo));
  botonPptx.classList.toggle("btn--secundario", !listo);
  $("btn-enviar").disabled = !listo;
  botonPptx.title = listo ? "Descarga el PowerPoint para el equipo de publicación" : "Se habilita cuando las 4 piezas están aprobadas";
}

function renderInvestigacion(inv) {
  if (!inv) return null;
  const fuente = inv.fuente_url && inv.fuente_url.startsWith("https://")
    ? el("a", { href: inv.fuente_url, target: "_blank", rel: "noopener noreferrer" }, inv.fuente_titulo || inv.fuente_url)
    : (inv.fuente_titulo || "Sin fuente");
  return el("section", { clase: "bloque" },
    el("h3", {}, "Investigación"),
    el("div", { clase: "investigacion" },
      el("p", { clase: "investigacion__tendencia" }, inv.tendencia),
      el("p", {}, inv.resumen),
      inv.estrategia_clave ? el("p", {}, el("strong", {}, "Estrategia clave: "), inv.estrategia_clave) : null,
      el("p", { clase: "investigacion__fuente" }, "Fuente: ", fuente, inv.fuente_fecha ? ` · ${inv.fuente_fecha}` : ""),
    ));
}

function renderTextos(pieza) {
  const c = pieza.contenido;
  const items = CAMPOS[pieza.formato].map(({ campo, rol, max }, i) => {
    const n = contarPalabras(c[campo]);
    return el("li", { clase: `texto-item${i === 0 ? " texto-item--gancho" : ""}` },
      el("span", { clase: "texto-item__num", "aria-hidden": "true" }, String(i + 1)),
      el("div", {},
        el("span", { clase: "texto-item__rol" }, `${pieza.formato === "Reel" ? "Escena" : "Tarjeta"} ${i + 1} · ${rol}`),
        el("p", { clase: "texto-item__texto" }, c[campo] || "—")),
      el("span", { clase: `contador${n > max ? " contador--excede" : ""}`, title: "Palabras usadas / máximo" }, `${n}/${max} palabras`));
  });
  const titulo = pieza.formato === "Reel" ? "Guion · texto en pantalla (30 s)" : "Tarjetas del carrusel";
  const boton = pieza.formato === "Carrusel" && pieza.id ? el("button", {
    clase: "btn btn--secundario", type: "button",
    title: "Vista previa de las 5 tarjetas como carrusel; desde ahí descargas el PDF editable",
    onclick: (ev) => verTarjetas(pieza.id, ev.currentTarget),
  }, "Ver tarjetas") : null;
  return el("section", { clase: "bloque" }, el("div", { clase: "bloque__titulo" }, el("h3", {}, titulo), boton), el("ol", { clase: "textos" }, items));
}

function renderCaption(c) {
  const cta = c.cta || "";
  let cuerpo = (c.caption || "").trim();
  if (cta && cuerpo.endsWith(cta)) cuerpo = cuerpo.slice(0, -cta.length).trim();
  const parrafos = cuerpo.split(/\n+/).filter(Boolean).map((t) => el("p", {}, t));
  return el("section", { clase: "bloque caption" },
    el("h3", {}, `Caption · ${contarPalabras(c.caption)} palabras`),
    parrafos,
    cta ? el("p", { clase: "caption__cta" }, cta) : null,
    (c.hashtags || []).length
      ? el("div", { clase: "hashtags", "aria-label": "Hashtags" }, c.hashtags.map((h) => el("span", { clase: "hashtag" }, h)))
      : el("p", { clase: "ayuda" }, "Sin hashtags: ninguno aportaba alcance."));
}

function renderAlertas(pieza) {
  const v = pieza.validacion || {};
  const nodos = [];
  if (pieza.error_msg) nodos.push(el("div", { clase: "alerta alerta--error", role: "alert" }, pieza.error_msg));
  if (v.errores?.length) {
    nodos.push(el("div", { clase: "alerta alerta--error" },
      el("strong", {}, "Incumple reglas (no se puede aprobar hasta corregirlo):"),
      el("ul", {}, v.errores.map((e) => el("li", {}, e)))));
  }
  if (v.advertencias?.length) {
    nodos.push(el("div", { clase: "alerta alerta--aviso" },
      el("strong", {}, "Para revisar:"),
      el("ul", {}, v.advertencias.map((e) => el("li", {}, e)))));
  }
  return nodos;
}

function renderComentarios(pieza, bloqueada) {
  const lista = (pieza.comentarios || []).map((c) => el("li", { clase: `comentario${c.aplicado_en ? " comentario--aplicado" : ""}` },
    el("div", {},
      el("p", { clase: "comentario__texto" }, c.texto),
      el("span", { clase: "comentario__estado" },
        c.aplicado_en ? `Aplicado en la versión ${c.version_resultante}` : "Pendiente · se aplica con «Aplicar ajustes»")),
    c.aplicado_en ? null : el("button", {
      clase: "btn btn--texto", type: "button", disabled: bloqueada, "aria-label": "Borrar comentario",
      onclick: () => accion(pieza.id, () => api(`comentarios?id=${c.id}`, { metodo: "DELETE" })),
    }, "Borrar")));

  const idCampo = `comentario-${pieza.id}`;
  const puedeComentar = pieza.estado === "generada" && !bloqueada;
  const campo = el("textarea", {
    id: idCampo, placeholder: "Ej.: Haz el gancho más directo y cambia la tarjeta 3 por un dato de Colombia.",
    disabled: !puedeComentar, maxlength: "2000",
    oninput: (ev) => { estado.borradores[pieza.id] = ev.target.value; },
  });
  campo.value = estado.borradores[pieza.id] || "";
  const form = el("form", {
    clase: "comentarios__form",
    onsubmit: (ev) => {
      ev.preventDefault();
      const texto = campo.value.trim();
      if (!texto) return;
      accion(pieza.id, async () => {
        await api("comentarios", { metodo: "POST", cuerpo: { pieza_id: pieza.id, texto } });
        delete estado.borradores[pieza.id];
      });
    },
  },
  el("label", { for: idCampo }, "Comentarios y ajustes"),
  campo,
  el("button", { clase: "btn btn--secundario", type: "submit", disabled: !puedeComentar }, "Agregar comentario"),
  pieza.estado === "aprobada" ? el("p", { clase: "ayuda" }, "Para comentar, primero desmarca «Aprobado».") : null);

  return el("section", { clase: "bloque comentarios" },
    el("h3", {}, "Revisión"),
    lista.length ? el("ul", { clase: "comentarios__lista" }, lista) : null,
    form);
}

function motivoNoAprobable(pieza) {
  if (pieza.estado === "aprobada") return null;
  if (pieza.estado !== "generada") return "La pieza aún no está lista.";
  if (pieza.validacion?.errores?.length) return "Corrige los errores de reglas antes de aprobar.";
  if (pendientes(pieza).length) return "Aplica o borra los comentarios pendientes antes de aprobar.";
  return null;
}

function renderCabecera(pieza, bloqueada) {
  const aprobada = pieza.estado === "aprobada";
  const motivo = motivoNoAprobable(pieza);
  const desactivada = bloqueada || Boolean(motivo);
  const idFecha = `fecha-${pieza.id}`;
  return el("header", { clase: "pieza__cabecera" },
    el("div", { clase: "pieza__meta" },
      el("span", { clase: `etiqueta etiqueta--${pieza.formato.toLowerCase()}` }, pieza.formato),
      el("span", {}, `Semana ${pieza.semana}`), "·", el("span", {}, pieza.tipo),
      pieza.version ? el("span", { clase: "etiqueta etiqueta--estado" }, `v${pieza.version}`) : null),
    el("div", { clase: "pieza__controles" },
      el("label", { clase: "campo-fecha", for: idFecha }, "Publicación",
        el("input", {
          id: idFecha, type: "date", value: pieza.fecha_publicacion || "", disabled: bloqueada,
          onchange: (ev) => accion(pieza.id, () => api("fecha", { metodo: "POST", cuerpo: { pieza_id: pieza.id, fecha: ev.target.value } })),
        })),
      el("label", {
        clase: `aprobar${aprobada ? " aprobar--activo" : ""}${desactivada ? " aprobar--bloqueado" : ""}`,
        title: motivo || (aprobada ? "Desmarca para volver a editar" : "Marca si la pieza no necesita ajustes"),
      },
      el("input", {
        type: "checkbox", checked: aprobada, disabled: desactivada,
        onchange: (ev) => accion(pieza.id, () => api("aprobar", { metodo: "POST", cuerpo: { pieza_id: pieza.id, aprobada: ev.target.checked } })),
      }),
      aprobada ? "Aprobado" : "Aprobar")));
}

function renderProceso(pieza) {
  const textos = {
    pendiente: "En cola para generar…",
    generando: "Investigando tendencias y redactando la pieza (1-3 minutos)…",
    ajustando: "Aplicando tus comentarios…",
  };
  if (pieza.estado === "error") {
    return el("div", { clase: "estado-proceso" },
      el("div", { clase: "alerta alerta--error", role: "alert" }, pieza.error_msg || "La generación falló."),
      el("p", {}, el("button", {
        clase: "btn btn--primario", type: "button", disabled: estado.ocupadas.size > 0,
        onclick: () => generarPieza(pieza.id),
      }, "Reintentar")));
  }
  return el("div", { clase: "estado-proceso", role: "status" }, el("span", { clase: "giro", "aria-hidden": "true" }), textos[pieza.estado] || "Procesando…");
}

function renderPieza(pieza) {
  const enProceso = estado.ocupadas.has(pieza.id) || ["generando", "ajustando"].includes(pieza.estado);
  const bloqueada = enProceso;
  const c = pieza.contenido;
  const tarjeta = el("article", { clase: `pieza${pieza.estado === "aprobada" ? " pieza--aprobada" : ""}`, "aria-busy": enProceso ? "true" : null },
    renderCabecera(pieza, bloqueada));
  const cuerpo = el("div", { clase: "pieza__cuerpo" });
  if (!c || enProceso || pieza.estado === "error") {
    cuerpo.append(el("p", { clase: "ayuda" }, pieza.pilar));
    cuerpo.append(renderProceso(estado.ocupadas.has(pieza.id) && !["generando", "ajustando"].includes(pieza.estado)
      ? { ...pieza, estado: pieza.contenido ? "ajustando" : "generando" } : pieza));
  } else {
    cuerpo.append(
      el("div", { clase: "pieza__titulo" }, el("h2", {}, c.tema_especifico), el("p", {}, pieza.pilar)),
      ...renderAlertas(pieza),
      renderInvestigacion(c.investigacion),
      renderTextos(pieza),
      renderCaption(c),
      renderComentarios(pieza, bloqueada));
  }
  if (estado.mensajes[pieza.id]) {
    cuerpo.append(el("div", { clase: "alerta alerta--error", role: "alert" }, estado.mensajes[pieza.id]));
  }
  tarjeta.append(cuerpo);
  return tarjeta;
}

function render() {
  renderBarra();
  $("lista-piezas").replaceChildren(...estado.piezas.map(renderPieza));
}

// ---------- acciones ----------

async function cargarMes() {
  const datos = await api("mes-actual");
  estado.mesObjetivo = datos.mes_objetivo;
  estado.mes = datos.mes;
  estado.piezas = datos.piezas;
  render();
}

async function accion(piezaId, fn) {
  estado.mensajes[piezaId] = null;
  try {
    await fn();
  } catch (e) {
    estado.mensajes[piezaId] = e.message;
  }
  await cargarMes().catch((e) => aviso(`No se pudo actualizar: ${e.message}`));
}

async function procesar(piezaId, ruta) {
  estado.ocupadas.add(piezaId);
  estado.mensajes[piezaId] = null;
  render();
  try {
    await api(ruta, { metodo: "POST", cuerpo: { pieza_id: piezaId } });
  } catch (e) {
    estado.mensajes[piezaId] = e.message;
  } finally {
    estado.ocupadas.delete(piezaId);
    await cargarMes().catch(() => render());
  }
}

const generarPieza = (id) => procesar(id, "generar-pieza");

async function generarPendientes() {
  if (estado.generandoTodo) return;
  estado.generandoTodo = true;
  try {
    for (const pieza of estado.piezas.filter((p) => p.estado === "pendiente")) {
      aviso(`Generando la pieza de la semana ${pieza.semana}… Puedes dejar esta pestaña abierta.`);
      await generarPieza(pieza.id);
    }
  } finally {
    estado.generandoTodo = false;
    aviso("");
  }
}

$("btn-generar").addEventListener("click", async () => {
  $("btn-generar").disabled = true;
  try {
    await api("iniciar-mes", { metodo: "POST", cuerpo: { mes: estado.mesObjetivo } });
    await cargarMes();
    await generarPendientes();
  } catch (e) {
    aviso(`No se pudo iniciar el mes: ${e.message}`);
  } finally {
    $("btn-generar").disabled = false;
  }
});

$("btn-ajustes").addEventListener("click", async () => {
  const conComentarios = estado.piezas.filter((p) => pendientes(p).length && p.estado === "generada");
  for (const [i, pieza] of conComentarios.entries()) {
    aviso(`Aplicando ajustes ${i + 1} de ${conComentarios.length} (semana ${pieza.semana})…`);
    await procesar(pieza.id, "ajustar-pieza");
  }
  aviso("");
});

async function pedirArchivo(url, nombrePorDefecto) {
  const pedir = () => fetch(url, { headers: { Authorization: `Bearer ${Sesion.leer()?.access_token || ""}` } });
  let r = await pedir();
  if (r.status === 401 && Sesion.leer()?.refresh_token) {
    await authSupabase("refresh_token", { refresh_token: Sesion.leer().refresh_token });
    r = await pedir();
  }
  if (!r.ok) {
    const datos = await r.json().catch(() => ({}));
    throw new Error(datos.error || `Error ${r.status}`);
  }
  const nombre = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || nombrePorDefecto;
  return { nombre, url: URL.createObjectURL(await r.blob()) };
}

function guardarArchivo({ nombre, url }) {
  const enlace = el("a", { href: url, download: nombre });
  document.body.append(enlace);
  enlace.click();
  enlace.remove();
}

async function descargarArchivo(url, nombrePorDefecto) {
  const archivo = await pedirArchivo(url, nombrePorDefecto);
  guardarArchivo(archivo);
  setTimeout(() => URL.revokeObjectURL(archivo.url), 10000);
}

async function descargarPptx(mesIso) {
  const mes = (typeof mesIso === "string" ? mesIso : estado.mesObjetivo).slice(0, 7);
  const boton = $("btn-pptx");
  boton.disabled = true;
  aviso("Generando el PowerPoint…");
  try {
    await descargarArchivo(`/api/exportar-pptx?mes=${mes}`, "contenido.pptx");
    aviso("");
    await cargarMes();
  } catch (e) {
    aviso(`No se pudo generar el PowerPoint: ${e.message}`);
  } finally {
    renderBarra();
  }
}

let piezaTarjetas = null;

function tarjetaActual() {
  const pista = $("tarjetas-pista");
  return Math.round(pista.scrollLeft / pista.clientWidth);
}

function irATarjeta(i) {
  const pista = $("tarjetas-pista");
  const n = pista.children.length;
  pista.scrollTo({ left: Math.max(0, Math.min(n - 1, i)) * pista.clientWidth, behavior: "smooth" });
}

function actualizarCarrusel() {
  const n = $("tarjetas-pista").children.length;
  const i = tarjetaActual();
  $("tarjetas-contador").textContent = `Tarjeta ${i + 1} de ${n}`;
  $("tarjetas-ant").disabled = i <= 0;
  $("tarjetas-sig").disabled = i >= n - 1;
}

async function verTarjetas(piezaId, boton) {
  boton.disabled = true;
  const texto = boton.textContent;
  boton.textContent = "Generando vista previa…";
  try {
    const { imagenes } = await api(`tarjetas-vista?pieza=${piezaId}`);
    piezaTarjetas = piezaId;
    $("tarjetas-pista").replaceChildren(...imagenes.map((src, i) => el("img", { src, alt: `Tarjeta ${i + 1} de ${imagenes.length}` })));
    $("dialogo-tarjetas").showModal();
    $("tarjetas-pista").scrollLeft = 0;
    actualizarCarrusel();
    $("tarjetas-pista").focus();
  } catch (e) {
    aviso(`No se pudo generar la vista previa: ${e.message}`);
  } finally {
    boton.disabled = false;
    boton.textContent = texto;
  }
}

$("tarjetas-pista").addEventListener("scroll", actualizarCarrusel, { passive: true });
$("tarjetas-ant").addEventListener("click", () => irATarjeta(tarjetaActual() - 1));
$("tarjetas-sig").addEventListener("click", () => irATarjeta(tarjetaActual() + 1));
$("dialogo-tarjetas").addEventListener("keydown", (ev) => {
  if (ev.key === "ArrowLeft") { ev.preventDefault(); irATarjeta(tarjetaActual() - 1); }
  if (ev.key === "ArrowRight") { ev.preventDefault(); irATarjeta(tarjetaActual() + 1); }
});
window.addEventListener("resize", () => { if ($("dialogo-tarjetas").open) irATarjeta(tarjetaActual()); });
$("tarjetas-cerrar").addEventListener("click", () => $("dialogo-tarjetas").close());
$("dialogo-tarjetas").addEventListener("close", () => $("tarjetas-pista").replaceChildren());
$("tarjetas-descargar").addEventListener("click", async (ev) => {
  const boton = ev.currentTarget;
  boton.disabled = true;
  try {
    await descargarArchivo(`/api/tarjetas-pdf?pieza=${piezaTarjetas}`, "tarjetas.pdf");
  } catch (e) {
    aviso(`No se pudo descargar el PDF: ${e.message}`);
  } finally {
    boton.disabled = false;
  }
});

$("btn-pptx").addEventListener("click", () => descargarPptx());

// ---------- repositorio ----------

const repo = { piezas: [], cargado: false, seleccion: null, versiones: [], version: null, marcadas: new Set() };
const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function fechaCorta(iso) {
  if (!iso) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {  // fecha sin hora: sin conversión de zona horaria
    const [a, m, d] = iso.split("-").map(Number);
    return `${d} ${MESES_CORTOS[m - 1]} ${a}`;
  }
  // Fecha con hora: se lleva a la fecha de Bogotá y se formatea igual que las fechas simples
  const partes = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit" })
    .format(new Date(iso));
  return fechaCorta(partes);
}

function opciones(select, valores, etiqueta = (v) => v) {
  const actual = select.value;
  select.replaceChildren(el("option", { value: "" }, "Todos"), ...valores.map((v) => el("option", { value: v }, etiqueta(v))));
  if (valores.includes(actual)) select.value = actual;
}

function filtrarRepo() {
  const mes = $("filtro-mes").value, formato = $("filtro-formato").value, pilar = $("filtro-pilar").value;
  const texto = $("filtro-texto").value.trim().toLowerCase();
  return repo.piezas.filter((p) => (!mes || (mes === "historico" ? p.historico : p.mes_objetivo === mes))
    && (!formato || p.formato === formato) && (!pilar || p.pilar === pilar)
    && (!texto || `${p.tema} ${p.tendencia}`.toLowerCase().includes(texto)));
}

function renderRepo() {
  const meses = [...new Set(repo.piezas.filter((p) => !p.historico).map((p) => p.mes_objetivo))];
  opciones($("filtro-mes"), [...meses, ...(repo.piezas.some((p) => p.historico) ? ["historico"] : [])],
    (v) => (v === "historico" ? "Histórico (antes de la app)" : nombreMes(v)));
  opciones($("filtro-pilar"), [...new Set(repo.piezas.filter((p) => !p.historico).map((p) => p.pilar))]);

  const filas = filtrarRepo();
  const entregados = new Set(repo.piezas.filter((p) => p.estado_mes === "entregado").map((p) => p.mes_objetivo)).size;
  $("resumen-repo").textContent = `${repo.piezas.length} contenidos · ${entregados} ${entregados === 1 ? "mes entregado" : "meses entregados"}`
    + (filas.length !== repo.piezas.length ? ` · mostrando ${filas.length}` : "");

  const cuerpo = $("cuerpo-repo");
  repo.marcadas = new Set([...repo.marcadas].filter((id) => repo.piezas.some((p) => p.id === id)));
  $("btn-borrar-repo").disabled = repo.marcadas.size === 0;
  $("btn-borrar-repo").textContent = repo.marcadas.size ? `Borrar seleccionados (${repo.marcadas.size})` : "Borrar seleccionados";
  const todos = $("repo-todos");
  todos.checked = filas.length > 0 && filas.every((p) => repo.marcadas.has(p.id));
  if (!filas.length) {
    cuerpo.replaceChildren(el("tr", {}, el("td", { colspan: "9", clase: "vacio" }, "No hay contenidos con esos filtros.")));
    return;
  }
  cuerpo.replaceChildren(...filas.map((p) => {
    const abrir = () => abrirDetalle(p.id);
    return el("tr", {
      tabindex: "0", "aria-selected": repo.seleccion === p.id ? "true" : "false",
      onclick: abrir, onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrir(); } },
    },
    el("td", { clase: "col-check", onclick: (ev) => ev.stopPropagation(), onkeydown: (ev) => ev.stopPropagation() },
      el("input", {
        type: "checkbox", checked: repo.marcadas.has(p.id), "aria-label": `Seleccionar ${p.tema}`,
        onchange: (ev) => { if (ev.target.checked) repo.marcadas.add(p.id); else repo.marcadas.delete(p.id); renderRepo(); },
      })),
    el("td", { clase: "tenue" }, p.historico ? "Histórico" : nombreMes(p.mes_objetivo)),
    el("td", { clase: "tenue" }, p.historico ? "—" : fechaCorta(p.fecha_publicacion)),
    el("td", {}, p.historico ? "—" : el("span", { clase: `etiqueta etiqueta--${p.formato.toLowerCase()}` }, p.formato)),
    el("td", { clase: "tema" }, p.tema),
    el("td", {}, p.historico ? "—" : `${p.tipo} · ${p.pilar}`),
    el("td", { clase: "tenue" }, p.historico ? "—" : fechaCorta(p.creado_en)),
    el("td", { clase: "tenue" }, p.historico ? "—" : fechaCorta(p.aprobada_en)),
    el("td", { clase: "tenue" }, p.historico ? "—" : fechaCorta(p.mes_entregado_en)));
  }));
}

async function cargarRepositorio() {
  $("resumen-repo").textContent = "Cargando…";
  try {
    repo.piezas = (await api("repositorio")).piezas;
    repo.cargado = true;
    renderRepo();
  } catch (e) {
    $("resumen-repo").textContent = `No se pudo cargar el repositorio: ${e.message}`;
  }
}

function renderDetalle() {
  const nodo = $("detalle-repo");
  const p = repo.piezas.find((x) => x.id === repo.seleccion);
  if (!p) { nodo.hidden = true; return; }
  const version = repo.versiones.find((v) => v.version === repo.version);
  const vista = { ...p, contenido: version ? version.contenido : p.contenido };
  const cuerpo = el("div", { clase: "pieza__cuerpo" });
  if (p.historico) {
    cuerpo.append(el("div", { clase: "pieza__titulo" }, el("h2", {}, p.tema),
      el("p", {}, "Tema publicado antes de la app. Se usa para no repetir contenidos.")));
  } else {
    cuerpo.append(
      el("div", { clase: "pieza__titulo" }, el("h2", {}, vista.contenido.tema_especifico), el("p", {}, p.pilar)),
      repo.versiones.length > 1 ? el("div", { clase: "versiones", role: "group", "aria-label": "Versiones" },
        el("span", { clase: "ayuda" }, "Versiones:"),
        repo.versiones.map((v) => el("button", {
          clase: "version-btn", type: "button", "aria-pressed": v.version === repo.version ? "true" : "false",
          onclick: () => { repo.version = v.version; renderDetalle(); },
        }, `v${v.version} · ${v.motivo === "generacion" ? "original" : v.motivo} · ${fechaCorta(v.creado_en)}`))) : null,
      renderInvestigacion(vista.contenido.investigacion),
      renderTextos(vista),
      renderCaption(vista.contenido));
  }
  const acciones = el("div", { clase: "pieza__controles" },
    !p.historico && p.estado_mes !== "historico" ? el("button", {
      clase: "btn btn--primario", type: "button",
      onclick: () => descargarPptx(p.mes_objetivo),
    }, `Descargar PowerPoint de ${nombreMes(p.mes_objetivo)}`) : null,
    !p.historico && ["aprobado", "entregado"].includes(p.estado_mes) ? el("button", {
      clase: "btn btn--secundario", type: "button", onclick: () => abrirEnvio(p.mes_objetivo),
    }, "Enviar por correo") : null,
    el("button", { clase: "btn btn--peligro", type: "button", onclick: () => borrarPiezas([p.id]) }, "Borrar"),
    el("button", { clase: "btn btn--secundario", type: "button", onclick: () => { repo.seleccion = null; renderDetalle(); renderRepo(); } }, "Cerrar"));
  nodo.replaceChildren(el("article", { clase: "pieza" },
    el("header", { clase: "pieza__cabecera" },
      el("div", { clase: "pieza__meta" },
        p.historico ? el("span", { clase: "etiqueta etiqueta--estado" }, "Histórico")
          : [el("span", { clase: `etiqueta etiqueta--${p.formato.toLowerCase()}` }, p.formato),
            el("span", {}, `Semana ${p.semana} · ${p.tipo} · Publicación ${fechaCorta(p.fecha_publicacion)}`)]),
      acciones),
    cuerpo));
  nodo.hidden = false;
}

async function abrirDetalle(id) {
  repo.seleccion = id;
  repo.versiones = [];
  repo.version = null;
  renderRepo();
  renderDetalle();
  $("detalle-repo").scrollIntoView({ behavior: "smooth", block: "start" });
  const p = repo.piezas.find((x) => x.id === id);
  if (p && !p.historico) {
    try {
      repo.versiones = (await api(`versiones?pieza_id=${id}`)).versiones;
      repo.version = repo.versiones[0]?.version ?? null;
      if (repo.seleccion === id) renderDetalle();
    } catch { /* el detalle ya muestra la versión vigente */ }
  }
}

async function borrarPiezas(ids) {
  const temas = ids.map((id) => repo.piezas.find((p) => p.id === id)?.tema).filter(Boolean);
  const detalle = temas.length <= 3 ? `\n\n• ${temas.join("\n• ")}` : `\n\n(${temas.length} contenidos)`;
  if (!window.confirm(`¿Borrar ${ids.length === 1 ? "este contenido" : `estos ${ids.length} contenidos`} del repositorio?`
    + `${detalle}\n\nSe borran también sus versiones y comentarios, y el tema podrá volver a proponerse. No se puede deshacer.`)) return;
  try {
    await api("borrar-piezas", { metodo: "POST", cuerpo: { ids } });
    repo.marcadas.clear();
    if (ids.includes(repo.seleccion)) repo.seleccion = null;
    await cargarRepositorio();
    renderDetalle();
    aviso(`Se borró ${ids.length === 1 ? "1 contenido" : `${ids.length} contenidos`} del repositorio.`);
  } catch (e) {
    aviso(`No se pudo borrar: ${e.message}`);
  }
}

$("btn-borrar-repo").addEventListener("click", () => borrarPiezas([...repo.marcadas]));
$("repo-todos").addEventListener("change", (ev) => {
  for (const p of filtrarRepo()) { if (ev.target.checked) repo.marcadas.add(p.id); else repo.marcadas.delete(p.id); }
  renderRepo();
});

["filtro-mes", "filtro-formato", "filtro-pilar", "filtro-texto"].forEach((id) => $(id).addEventListener("input", renderRepo));
$("filtros-repo").addEventListener("submit", (ev) => ev.preventDefault());

function mostrarSeccion(nombre) {
  const esRepo = nombre === "repositorio", esConfig = nombre === "configuracion";
  $("seccion-propuestas").hidden = esRepo || esConfig;
  $("seccion-repositorio").hidden = !esRepo;
  $("seccion-configuracion").hidden = !esConfig;
  for (const [id, activa] of [["tab-propuestas", nombre === "propuestas"], ["tab-repositorio", esRepo], ["tab-configuracion", esConfig]]) {
    $(id).classList.toggle("pestana--activa", activa);
    if (activa) $(id).setAttribute("aria-current", "page"); else $(id).removeAttribute("aria-current");
  }
  if (esRepo) cargarRepositorio();
  if (esConfig) cargarConfiguracion();
}

$("tab-propuestas").addEventListener("click", () => mostrarSeccion("propuestas"));
$("tab-repositorio").addEventListener("click", () => mostrarSeccion("repositorio"));
$("tab-configuracion").addEventListener("click", () => mostrarSeccion("configuracion"));

// ---------- configuración: fuentes y correos favoritos ----------

const cfg = { fuentes: [], recomendadas: [], favoritos: [], correoConfigurado: false, teamsConfigurado: false, cargada: false };

function msgConfig(texto, error = false) {
  const nodo = $("mensaje-config");
  nodo.textContent = texto || "";
  nodo.className = `mensaje${error ? " mensaje--error" : ""}`;
}

function renderConfig() {
  const filtro = $("buscar-fuente").value.trim().toLowerCase();
  const visibles = cfg.fuentes.filter((d) => d.includes(filtro));
  $("resumen-fuentes").textContent = `${cfg.fuentes.length} fuentes`
    + (filtro ? ` · mostrando ${visibles.length}` : "")
    + (cfg.fuentes.length <= 1 ? " · debe quedar al menos una" : "");
  $("lista-fuentes").replaceChildren(...visibles.map((d) => el("li", { clase: "chip" }, d,
    el("button", { type: "button", "aria-label": `Quitar ${d}`, title: "Quitar", disabled: cfg.fuentes.length <= 1,
      onclick: () => cambiarConfig(() => api(`fuentes?dominio=${encodeURIComponent(d)}`, { metodo: "DELETE" }), `Se quitó ${d}.`) }, "×"))));
  $("lista-favoritos").replaceChildren(...(cfg.favoritos.length ? cfg.favoritos.map((f) => el("li", { clase: "favorito" },
    el("div", {}, f.nombre ? el("strong", {}, f.nombre) : null, el("small", {}, f.email)),
    el("button", { clase: "btn btn--peligro", type: "button", "aria-label": `Quitar ${f.email}`,
      onclick: () => cambiarConfig(() => api(`favoritos?id=${f.id}`, { metodo: "DELETE" }), `Se quitó ${f.email}.`) }, "Quitar")))
    : [el("li", { clase: "ayuda" }, "Aún no tienes correos favoritos.")]));
  const aviso = $("estado-correo");
  aviso.hidden = cfg.correoConfigurado;
  aviso.textContent = "El envío por correo aún no está activado: falta configurar SMTP_USER y SMTP_PASSWORD en Vercel (ver README).";
  $("estado-teams").hidden = cfg.teamsConfigurado;
  $("estado-teams").textContent = "El aviso a Teams aún no está activado: falta configurar TEAMS_WEBHOOK_URL en Vercel (ver README).";
}

$("btn-probar-teams").addEventListener("click", async (ev) => {
  ev.currentTarget.disabled = true;
  try {
    await api("probar-teams", { metodo: "POST", cuerpo: {} });
    msgConfig("Mensaje de prueba enviado: revisa el canal de Teams.");
  } catch (e) {
    msgConfig(e.message, true);
  } finally {
    ev.currentTarget.disabled = false;
  }
});

async function cargarConfiguracion() {
  try {
    const d = await api("configuracion");
    Object.assign(cfg, { fuentes: d.fuentes, recomendadas: d.recomendadas, favoritos: d.favoritos,
      correoConfigurado: d.correo_configurado, teamsConfigurado: d.teams_configurado, cargada: true });
    renderConfig();
  } catch (e) {
    msgConfig(`No se pudo cargar la configuración: ${e.message}`, true);
  }
}

async function cambiarConfig(accion, exito) {
  msgConfig("");
  try {
    await accion();
    await cargarConfiguracion();
    msgConfig(exito);
  } catch (e) {
    msgConfig(e.message, true);
  }
}

$("form-fuente").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const dominio = $("nueva-fuente").value;
  cambiarConfig(async () => {
    await api("fuentes", { metodo: "POST", cuerpo: { dominio } });
    $("nueva-fuente").value = "";
  }, "Fuente agregada.");
});
$("buscar-fuente").addEventListener("input", renderConfig);
$("btn-restaurar").addEventListener("click", async () => {
  msgConfig("");
  try {
    const r = await api("fuentes-restaurar", { metodo: "POST", cuerpo: {} });
    await cargarConfiguracion();
    msgConfig(r.agregadas ? `Se restauraron ${r.agregadas} fuentes recomendadas.` : "Ya tienes todas las recomendadas.");
  } catch (e) { msgConfig(e.message, true); }
});
$("form-favorito").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const email = $("nuevo-correo").value, nombre = $("nuevo-nombre").value;
  cambiarConfig(async () => {
    await api("favoritos", { metodo: "POST", cuerpo: { email, nombre } });
    $("nuevo-correo").value = "";
    $("nuevo-nombre").value = "";
  }, "Correo agregado a favoritos.");
});

// ---------- envío del PowerPoint por correo ----------

let mesEnvio = null;

async function abrirEnvio(mesIso) {
  mesEnvio = (mesIso || estado.mesObjetivo).slice(0, 7);
  if (!cfg.cargada) await cargarConfiguracion();
  $("resumen-envio").textContent = `Se enviará el PowerPoint de ${nombreMes(`${mesEnvio}-01`)} como adjunto.`
    + (cfg.correoConfigurado ? "" : " Atención: el envío aún no está activado en el servidor.");
  $("envio-favoritos").replaceChildren(...(cfg.favoritos.length ? cfg.favoritos.map((f, i) => el("label", { clase: "opcion-favorito" },
    el("input", { type: "checkbox", name: "favorito", value: f.email }),
    f.nombre ? `${f.nombre} · ${f.email}` : f.email))
    : [el("p", { clase: "ayuda" }, "Aún no tienes favoritos: agrégalos en Configuración o escribe los correos abajo.")]));
  $("envio-otros").value = "";
  $("envio-mensaje").value = "";
  $("envio-guardar").checked = false;
  $("error-envio").textContent = "";
  $("envio-enviar").disabled = false;
  $("dialogo-envio").showModal();
}

$("form-envio").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const favoritos = [...document.querySelectorAll('#envio-favoritos input[name="favorito"]:checked')].map((i) => i.value);
  const otros = $("envio-otros").value.trim();
  if (!favoritos.length && !otros) { $("error-envio").textContent = "Elige al menos un destinatario."; return; }
  $("envio-enviar").disabled = true;
  $("error-envio").textContent = "";
  $("envio-enviar").textContent = "Enviando…";
  try {
    const r = await api("enviar-pptx", { metodo: "POST", cuerpo: {
      mes: mesEnvio, favoritos, otros, mensaje: $("envio-mensaje").value, guardar_favoritos: $("envio-guardar").checked } });
    $("dialogo-envio").close();
    aviso(`PowerPoint enviado a ${r.enviados.join(", ")}.`);
    cfg.cargada = false;
    await cargarMes();
    if (!$("seccion-repositorio").hidden) await cargarRepositorio();
  } catch (e) {
    $("error-envio").textContent = e.message;
  } finally {
    $("envio-enviar").disabled = false;
    $("envio-enviar").textContent = "Enviar";
  }
});
$("envio-cancelar").addEventListener("click", () => $("dialogo-envio").close());
$("btn-enviar").addEventListener("click", () => abrirEnvio());

// ---------- login ----------

function mostrar(vista) {
  $("vista-login").hidden = vista !== "login";
  $("vista-app").hidden = vista !== "app";
  $("btn-salir").hidden = vista !== "app";
}

async function entrarApp() {
  try {
    await api("yo");
  } catch (e) {
    if (e.estado === 401) { Sesion.borrar(); mostrar("login"); return; }
    mostrar("app");
    aviso(`Error: ${e.message}`);
    return;
  }
  mostrar("app");
  try {
    await cargarMes();
    if (estado.piezas.some((p) => p.estado === "pendiente")) generarPendientes();
  } catch (e) {
    aviso(`No se pudieron cargar las propuestas: ${e.message}`);
  }
}

$("form-login").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("login-error").textContent = "";
  try {
    await authSupabase("password", { email: $("email").value.trim(), password: $("clave").value });
    await entrarApp();
  } catch (e) {
    $("login-error").textContent = e.message;
  }
});

$("btn-salir").addEventListener("click", () => { Sesion.borrar(); mostrar("login"); });

(async () => {
  try {
    await cargarConfig();
  } catch (e) {
    mostrar("login");
    $("login-error").textContent = e.message;
    return;
  }
  if (Sesion.leer()) await entrarApp(); else mostrar("login");
})();

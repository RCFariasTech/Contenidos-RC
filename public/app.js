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
  return el("section", { clase: "bloque" }, el("h3", {}, titulo), el("ol", { clase: "textos" }, items));
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
    el("div", { clase: "hashtags", "aria-label": "Hashtags" }, (c.hashtags || []).map((h) => el("span", { clase: "hashtag" }, h))));
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

async function descargarPptx() {
  const boton = $("btn-pptx");
  boton.disabled = true;
  aviso("Generando el PowerPoint…");
  try {
    let r = await fetch(`/api/exportar-pptx?mes=${estado.mesObjetivo.slice(0, 7)}`, {
      headers: { Authorization: `Bearer ${Sesion.leer()?.access_token || ""}` },
    });
    if (r.status === 401 && Sesion.leer()?.refresh_token) {
      await authSupabase("refresh_token", { refresh_token: Sesion.leer().refresh_token });
      r = await fetch(`/api/exportar-pptx?mes=${estado.mesObjetivo.slice(0, 7)}`, {
        headers: { Authorization: `Bearer ${Sesion.leer()?.access_token || ""}` },
      });
    }
    if (!r.ok) {
      const datos = await r.json().catch(() => ({}));
      throw new Error(datos.error || `Error ${r.status}`);
    }
    const nombre = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "contenido.pptx";
    const url = URL.createObjectURL(await r.blob());
    const enlace = el("a", { href: url, download: nombre });
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    aviso("");
    await cargarMes();
  } catch (e) {
    aviso(`No se pudo generar el PowerPoint: ${e.message}`);
  } finally {
    renderBarra();
  }
}

$("btn-pptx").addEventListener("click", descargarPptx);

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

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

async function api(ruta, { metodo = "GET", cuerpo, senal } = {}, reintentar = true) {
  const sesion = Sesion.leer();
  const opciones = {
    method: metodo,
    headers: { Authorization: `Bearer ${sesion?.access_token || ""}` },
    signal: senal,
  };
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  const r = await fetch(`/api/${ruta}`, opciones);
  if (r.status === 401 && reintentar && sesion?.refresh_token) {
    try {
      await authSupabase("refresh_token", { refresh_token: sesion.refresh_token });
      return api(ruta, { metodo, cuerpo, senal }, false);
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
    { campo: "escena_1_gancho", rol: "Gancho", max: 8 },
    { campo: "escena_2_desarrollo_a", rol: "Desarrollo", max: 15 },
    { campo: "escena_3_desarrollo_b", rol: "Desarrollo", max: 15 },
    { campo: "escena_4_desarrollo_c", rol: "Desarrollo", max: 15 },
    { campo: "escena_5_cta", rol: "CTA", max: 10 },
  ],
};

const ESTADOS_MES = {
  generando: "Generando propuestas", en_revision: "En revisión", aprobado: "Aprobado",
  entregado: "Entregado", historico: "Histórico",
};

// ---------- estado de la vista ----------

const estado = { mes: null, piezas: [], ocupadas: new Set(), mensajes: {}, borradores: {}, generandoTodo: false,
  expandidas: new Set() };  // piezas aprobadas que el usuario abrió (por defecto se ven contraídas)

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
  // Aviso para Daniela y Luís: qué falta para que se abra su etapa.
  const etapaRol = { diseno: ["textos", "Reini", "los textos"], publicacion: ["diseno", "Daniela", "el diseño"] }[estado.rol];
  let avisoEtapa = "";
  if (etapaRol && piezas.length) {
    const [previa, quien, que] = etapaRol;
    const faltan = piezas.filter((p) => (previa === "textos" ? p.estado !== "aprobada" : !p.aprobaciones?.[previa]));
    avisoEtapa = faltan.length
      ? `Tu revisión se habilita cuando ${quien} apruebe ${que} de las ${piezas.length} piezas. Falta: ${faltan.map((p) => `semana ${p.semana} (${p.formato.toLowerCase()})`).join(", ")}.`
      : "Tu etapa está abierta: revisa y aprueba cada pieza.";
  }
  $("aviso-etapa").hidden = !avisoEtapa;
  $("aviso-etapa").textContent = avisoEtapa;
  const conComentarios = piezas.filter((p) => pendientes(p).length && p.estado === "generada").length;
  const botonAjustes = $("btn-ajustes");
  botonAjustes.textContent = conComentarios ? `Aplicar ajustes (${conComentarios})` : "Aplicar ajustes";
  botonAjustes.disabled = !conComentarios || estado.ocupadas.size > 0;
}

const investigacionAbierta = new Set();  // piezas cuya investigación el usuario dejó desplegada (sobrevive a los re-render)

function renderInvestigacion(inv, piezaId) {
  if (!inv) return null;
  const fuente = inv.fuente_url && inv.fuente_url.startsWith("https://")
    ? el("a", { href: inv.fuente_url, target: "_blank", rel: "noopener noreferrer" }, inv.fuente_titulo || inv.fuente_url)
    : (inv.fuente_titulo || "Sin fuente");
  return el("details", {
    clase: "bloque desplegable", open: investigacionAbierta.has(piezaId),
    ontoggle: (ev) => { if (ev.currentTarget.open) investigacionAbierta.add(piezaId); else investigacionAbierta.delete(piezaId); },
  },
    el("summary", {}, el("h3", {}, "Investigación"), el("span", { clase: "desplegable__pista" }, inv.tendencia)),
    el("div", { clase: "investigacion" },
      el("p", { clase: "investigacion__tendencia" }, inv.tendencia),
      el("p", {}, inv.resumen),
      inv.estrategia_clave ? el("p", {}, el("strong", {}, "Estrategia clave: "), inv.estrategia_clave) : null,
      el("p", { clase: "investigacion__fuente" }, "Fuente: ", fuente, inv.fuente_fecha ? ` · ${inv.fuente_fecha}` : ""),
    ));
}

// ---------- miniaturas de las propuestas gráficas (junto a cada texto) ----------

const miniaturas = { cache: new Map(), pendientes: new Set(), semillas: new Map(), piezas: new Map(), rev: new Map() };
const semillaDe = (piezaId) => miniaturas.semillas.get(piezaId) || 0;
const claveVista = (p) => `${p.id}:${p.version}:${semillaDe(p.id)}:${miniaturas.rev.get(p.id) || 0}`;

function pintarMiniatura(caja, pieza) {
  const dato = miniaturas.cache.get(claveVista(pieza));
  const i = Number(caja.dataset.indice);
  caja.classList.toggle("miniatura--cargando", !dato);
  if (!dato) {
    caja.replaceChildren();
  } else if (dato.imagenes?.[i]) {
    caja.replaceChildren(el("img", { src: dato.imagenes[i], alt: "", loading: "lazy" }));
  } else {
    caja.replaceChildren(el("span", {}, "Sin vista previa"));
  }
}

function repintarMiniaturas(piezaId) {
  const pieza = miniaturas.piezas.get(piezaId);
  if (!pieza) return;
  document.querySelectorAll(`.miniatura[data-pieza="${piezaId}"]`).forEach((caja) => pintarMiniatura(caja, pieza));
}

function pedirMiniaturas(pieza) {
  const clave = claveVista(pieza);
  if (miniaturas.cache.has(clave) || miniaturas.pendientes.has(clave)) return;
  miniaturas.pendientes.add(clave);
  api(`tarjetas-vista?pieza=${pieza.id}&semilla=${semillaDe(pieza.id)}&ancho=360`)
    .then((datos) => {
      miniaturas.cache.set(clave, datos);
      // Imágenes automáticas de Krea aún en camino: se vuelve a pedir la vista en unos segundos.
      if (datos.imagenes_en_cola > 0) setTimeout(() => refrescarMiniaturasDe(pieza), 15000);
    })
    .catch(() => miniaturas.cache.set(clave, { error: true }))
    .finally(() => { miniaturas.pendientes.delete(clave); repintarMiniaturas(pieza.id); });
}

function miniatura(pieza, i) {
  const reel = pieza.formato === "Reel";
  const caja = el("button", {
    clase: "miniatura", type: "button", "data-pieza": pieza.id, "data-indice": i,
    style: `aspect-ratio: ${reel ? "9 / 16" : "4 / 5"}; width: ${reel ? 84 : 112}px`,
    title: "Ver en grande",
    "aria-label": `Ver la propuesta gráfica de la ${reel ? "escena" : "tarjeta"} ${i + 1} en grande`,
    onclick: (ev) => (reel ? window.abrirReel(pieza, { reproducir: true, desde: i }) : verTarjetas(pieza.id, ev.currentTarget, i)),
  });
  miniaturas.piezas.set(pieza.id, pieza);
  pintarMiniatura(caja, pieza);
  pedirMiniaturas(pieza);
  return caja;
}

function renderTextos(pieza, conMiniaturas = true) {
  const c = pieza.contenido;
  conMiniaturas = conMiniaturas && Boolean(pieza.id) && pieza.version != null;
  const items = CAMPOS[pieza.formato].map(({ campo, rol, max }, i) => {
    const n = contarPalabras(c[campo]);
    return el("li", { clase: `texto-item${i === 0 ? " texto-item--gancho" : ""}${conMiniaturas ? " texto-item--miniatura" : ""}` },
      el("span", { clase: "texto-item__num", "aria-hidden": "true" }, String(i + 1)),
      el("div", {},
        el("span", { clase: "texto-item__rol" }, `${pieza.formato === "Reel" ? "Escena" : "Tarjeta"} ${i + 1} · ${rol}`),
        estado.editando === `${pieza.id}:${campo}` ? editorTexto(pieza, campo, max)
          : textoEditable(pieza, campo, el("p", { clase: "texto-item__texto" }, c[campo] || "—")),
        i === 0 && pieza.id && pieza.estado === "generada" && estado.editando !== `${pieza.id}:${campo}`
          ? el("div", { clase: "gancho-acciones" },
            el("button", {
              clase: "btn btn--secundario btn--chico", type: "button",
              title: "Propone con IA un gancho nuevo, distinto de los anteriores (guarda una versión nueva)",
              onclick: () => procesar(pieza.id, "regenerar-gancho"),
            }, "Otro gancho"),
            null)
          : null,
        conMiniaturas && opcionCifra(pieza, i + 1) ? selectorCifra(pieza, i + 1, c[campo] || "") : null,
        conMiniaturas && opcionFoto(pieza, i + 1) ? el("label", { clase: "reel-foto",
          title: "La escena muestra una foto de apoyo con velo de color en vez del ícono de línea" },
          el("input", { type: "checkbox", checked: (pieza.diseno_reel?.fotos || []).includes(i + 1),
            disabled: pieza.estado === "aprobada",
            onchange: (ev) => accion(pieza.id, () => api("reel-foto", { metodo: "POST",
              cuerpo: { pieza_id: pieza.id, escena: i + 1, activa: ev.target.checked } })).then(() => refrescarMiniaturasDe(pieza)) }),
          " Usar foto en esta escena") : null,
        conMiniaturas && infoImagen(pieza, i + 1) ? el("button", {
          clase: "btn btn--secundario btn--chico", type: "button",
          title: infoImagen(pieza, i + 1).ayuda,
          onclick: () => abrirIlustraciones(pieza, i + 1, c[campo] || ""),
        }, infoImagen(pieza, i + 1).boton) : null),
      el("span", { clase: `contador${n > max ? " contador--excede" : ""}`, title: "Palabras usadas / máximo" }, `${n}/${max} palabras`),
      conMiniaturas ? miniatura(pieza, i) : null);
  });
  const titulo = pieza.formato === "Reel" ? "Guion · texto en pantalla" : "Tarjetas del carrusel";
  const boton = pieza.id ? el("button", {
    clase: "btn btn--secundario", type: "button",
    title: pieza.formato === "Reel" ? "Reproduce el reel completo (transiciones y textos animados); desde ahí descargas el video o el PDF del guion" : "Vista previa de las 5 tarjetas como carrusel; desde ahí descargas el PDF editable",
    onclick: (ev) => (pieza.formato === "Reel" ? window.abrirReel(pieza, { reproducir: true }) : verTarjetas(pieza.id, ev.currentTarget)),
  }, pieza.formato === "Reel" ? "Ver reel" : "Ver tarjetas") : null;
  const reel = pieza.formato === "Reel";
  const rehacer = conMiniaturas ? el("button", {
    clase: "btn btn--secundario", type: "button",
    title: `Muestra otra propuesta gráfica de colores y estilos para ${reel ? "las escenas" : "las tarjetas"} (el texto no cambia)`,
    onclick: () => {
      miniaturas.semillas.set(pieza.id, semillaDe(pieza.id) + 1);
      repintarMiniaturas(pieza.id);  // vuelven a "cargando" y se piden con la nueva semilla
      pedirMiniaturas(pieza);
    },
  }, reel ? "Rehacer escenas" : "Rehacer tarjetas") : null;
  return el("section", { clase: "bloque" },
    el("div", { clase: "bloque__titulo" }, el("h3", {}, titulo), el("div", { clase: "bloque__botones" }, rehacer, boton)),
    el("ol", { clase: "textos" }, items));
}

function renderCaption(c, pieza = null) {
  if (pieza && estado.editando === `${pieza.id}:caption`) {
    return el("section", { clase: "bloque caption" }, el("h3", {}, "Caption"),
      editorTexto(pieza, "caption", estado.maxCaption || 150));
  }
  const cta = c.cta || "";
  let cuerpo = (c.caption || "").trim();
  if (cta && cuerpo.endsWith(cta)) cuerpo = cuerpo.slice(0, -cta.length).trim();
  const parrafos = textoEditable(pieza, "caption",
    el("div", { clase: "caption__cuerpo" }, ...cuerpo.split(/\n+/).filter(Boolean).map((t) => el("p", {}, t))));
  return el("section", { clase: "bloque caption" },
    el("div", { clase: "bloque__titulo" }, el("h3", {}, `Caption · ${contarPalabras(c.caption)} palabras`),
      null),
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
  el("div", { clase: "comentarios__acciones" },
    el("button", { clase: "btn btn--secundario", type: "submit", disabled: !puedeComentar }, "Agregar comentario"),
    el("button", {
      clase: "btn btn--secundario", type: "button", disabled: !puedeComentar,
      title: `Descarta esta propuesta y genera otra con un tema distinto (nuevos textos, ${pieza.formato === "Reel" ? "escenas" : "tarjetas"} y caption)`,
      onclick: () => {
        if (window.confirm("¿Rehacer esta propuesta desde cero con otro tema? Se investiga y se redacta de nuevo (1-3 minutos). La versión actual queda guardada en el Repositorio.")) {
          procesar(pieza.id, "rehacer-pieza");
        }
      },
    }, "Rehacer propuesta")),
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
      aprobada ? "Aprobado" : "Aprobar")),
    renderAprobaciones(pieza, bloqueada));
}

// ---------- aprobaciones en 3 tiempos: textos (Reini) → diseño (Daniela) → publicación (Luís) ----------

const NOMBRE_ROL = { admin: "Reini", diseno: "Daniela", publicacion: "Luís" };

function etapaCompleta(etapa) {
  const ok = (p) => (etapa === "textos" ? p.estado === "aprobada" : Boolean(p.aprobaciones?.[etapa]));
  return estado.piezas.length > 0 && estado.piezas.every(ok);
}

function renderAprobaciones(pieza, bloqueada) {
  const ap = pieza.aprobaciones || {}, rol = estado.rol;
  const chip = (texto, hecho, titulo) => el("span", { clase: `etapa${hecho ? " etapa--hecha" : ""}`, title: titulo },
    `${hecho ? "✓" : "○"} ${texto}`);
  const textosOk = pieza.estado === "aprobada";
  const puedeDiseno = (rol === "diseno" || rol === "admin") && textosOk && etapaCompleta("textos");
  const puedePublicar = (rol === "publicacion" || rol === "admin") && etapaCompleta("diseno");
  const marcar = (etapa, ruta, hecho, texto) => el("label", { clase: `aprobar${hecho ? " aprobar--activo" : ""}` },
    el("input", { type: "checkbox", checked: hecho, disabled: bloqueada,
      onchange: async (ev) => {
        const ok = ev.target.checked;
        await accion(pieza.id, () => api(ruta, { metodo: "POST", cuerpo: { pieza_id: pieza.id, aprobada: ok } }));
        if (ok && etapa === "diseno" && pieza.formato === "Reel") abrirMusica(pieza);
      } }), texto);
  const devolver = (destino) => el("button", { clase: "btn btn--texto btn--chico", type: "button", disabled: bloqueada,
    title: `Devuelve la pieza a ${destino} con un comentario`,
    onclick: () => {
      const nota = window.prompt(`¿Qué hay que corregir? La pieza vuelve a ${destino}.`);
      if (nota && nota.trim()) accion(pieza.id, () => api("devolver", { metodo: "POST", cuerpo: { pieza_id: pieza.id, nota } }));
    } }, "Devolver");
  return el("div", { clase: "aprobaciones" },
    chip("Textos · Reini", textosOk, "Investigación y textos"),
    chip("Diseño · Daniela", Boolean(ap.diseno), ap.diseno ? `Aprobado por ${ap.diseno.por}` : "Diseños y animaciones"),
    chip("Publicación · Luís", Boolean(ap.publicacion), ap.publicacion ? `Aprobado por ${ap.publicacion.por}` : "Aprobación final"),
    puedeDiseno && !ap.publicacion ? marcar("diseno", "aprobar-diseno", Boolean(ap.diseno), ap.diseno ? "Diseño aprobado" : "Aprobar diseño") : null,
    puedeDiseno && !ap.diseno && rol === "diseno" ? devolver("Reini (textos)") : null,
    puedeDiseno && pieza.formato === "Reel" ? el("button", { clase: "btn btn--secundario btn--chico", type: "button",
      title: "Escucha y elige la música del reel (o crea propuestas nuevas)", onclick: () => verMusica(pieza) },
      pieza.diseno_reel?.musica?.elegida != null ? "♪ Música elegida" : "♪ Música") : null,
    puedePublicar && ap.diseno ? marcar("publicacion", "aprobar-publicacion", Boolean(ap.publicacion), ap.publicacion ? "Publicación aprobada" : "Aprobar publicación") : null,
    puedePublicar && ap.diseno && !ap.publicacion ? devolver("Daniela (diseño)") : null,
    ap.publicacion && (rol === "publicacion" || rol === "admin") ? el("button", { clase: "btn btn--primario btn--chico", type: "button",
      onclick: (ev) => descargarParaPublicar(pieza, ev.currentTarget) }, "Descargar para publicar") : null,
    ap.devolucion ? el("p", { clase: "aprobaciones__nota" },
      `Devuelta a ${ap.devolucion.a === "diseno" ? "diseño" : "textos"} por ${ap.devolucion.por}: ${ap.devolucion.nota}`) : null);
}

// ---------- descarga para publicar ----------

async function pedirBinario(url) {
  const r = await fetch(url, { headers: { Authorization: `Bearer ${Sesion.leer()?.access_token || ""}` } });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
  return r.blob();
}

function cargarScript(src) {
  return new Promise((ok, mal) => {
    if (document.querySelector(`script[src="${src}"]`)) { ok(); return; }
    document.head.append(el("script", { src, onload: ok, onerror: () => mal(new Error(`No se pudo cargar ${src}`)) }));
  });
}

async function descargarParaPublicar(pieza, boton) {
  if (pieza.formato === "Reel") { window.abrirReel(pieza, { descargarPublicacion: true }); return; }
  const texto = boton.textContent;
  boton.disabled = true;
  try {
    boton.textContent = "Preparando tarjetas…";
    await Promise.all([cargarScript("https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"),
      cargarScript("https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js")]);
    const base = `Semana_${pieza.semana}`;
    const zip = new window.JSZip(), carpeta = zip.folder(`${base}_carrusel`);
    const pdf = new window.jspdf.jsPDF({ orientation: "portrait", unit: "px", format: [1080, 1350], hotfixes: ["px_scaling"] });
    for (let n = 1; n <= 5; n += 1) {
      boton.textContent = `Tarjeta ${n} de 5…`;
      const jpg = await pedirBinario(`/api/tarjeta-jpg?pieza=${pieza.id}&n=${n}`);
      const nombre = `${base}_tarjeta_${String(n).padStart(2, "0")}.jpg`;
      carpeta.file(nombre, jpg);
      const datos = new Uint8Array(await jpg.arrayBuffer());
      if (n > 1) pdf.addPage([1080, 1350], "portrait");
      pdf.addImage(datos, "JPEG", 0, 0, 1080, 1350);
    }
    carpeta.file(`${base}_carrusel_LinkedIn.pdf`, pdf.output("blob"));
    boton.textContent = "Comprimiendo…";
    const archivo = await zip.generateAsync({ type: "blob" });
    const a = el("a", { href: URL.createObjectURL(archivo), download: `${base}_carrusel.zip` });
    document.body.append(a); a.click(); a.remove();
  } catch (e) {
    aviso(`No se pudo descargar el carrusel: ${e.message}`);
  } finally {
    boton.disabled = false;
    boton.textContent = texto;
  }
}

// ---------- música del reel (al aprobar el diseño) ----------

const MUSICA = { pieza: null, timer: 0, reproductor: null };

async function abrirMusica(pieza) {
  MUSICA.pieza = pieza;
  $("musica-opciones").replaceChildren(el("p", { clase: "ayuda" }, "Creando 2 propuestas de música instrumental en Krea (1-2 minutos)…"));
  $("dialogo-musica").showModal();
  try {
    await api("musica", { metodo: "POST", cuerpo: { pieza_id: pieza.id } });
    consultarMusica();
  } catch (e) {
    $("musica-opciones").replaceChildren(el("p", { clase: "alerta alerta--error" }, `No se pudo crear la música: ${e.message}`));
  }
}

async function verMusica(pieza) {
  // Abre las propuestas que ya existen; si aún no hay, ofrece crearlas.
  MUSICA.pieza = pieza;
  $("musica-opciones").replaceChildren(el("p", { clase: "ayuda" }, "Cargando propuestas…"));
  $("dialogo-musica").showModal();
  const m = pieza.diseno_reel?.musica;
  if (m?.opciones?.length) { consultarMusica(); return; }
  $("musica-opciones").replaceChildren(el("p", { clase: "ayuda" }, "Este reel aún no tiene propuestas de música."),
    el("button", { clase: "btn btn--primario", type: "button", onclick: () => abrirMusica(pieza) }, "Crear 2 propuestas"));
}

async function consultarMusica() {
  clearTimeout(MUSICA.timer);
  if (!$("dialogo-musica").open) return;
  try {
    const m = await api("musica", { metodo: "POST", cuerpo: { pieza_id: MUSICA.pieza.id, consultar: true } });
    const opciones = m.opciones || [];
    $("musica-opciones").replaceChildren(...opciones.map((o, i) => el("div", { clase: "musica-opcion" },
      el("strong", {}, `Propuesta ${i + 1}${m.elegida === i ? " · ✓ en el video" : ""}`),
      o.estado === "lista" ? el("div", { clase: "musica-opcion__acciones" },
        el("button", { clase: "btn btn--secundario btn--chico", type: "button", onclick: (ev) => escucharMusica(i, ev.currentTarget) }, "▶ Escuchar"),
        el("button", { clase: "btn btn--primario btn--chico", type: "button", onclick: () => elegirMusica(i) }, "Usar en el video"))
        : el("span", { clase: "ayuda" }, o.estado === "en_cola" ? "Generando…" : (o.error || "No se pudo generar")))));
    if (opciones.some((o) => o.estado === "en_cola")) MUSICA.timer = setTimeout(consultarMusica, 5000);
  } catch (e) {
    $("musica-opciones").replaceChildren(el("p", { clase: "alerta alerta--error" }, e.message));
  }
}

async function escucharMusica(i, boton) {
  MUSICA.reproductor?.pause();
  if (boton.dataset.sonando) { delete boton.dataset.sonando; boton.textContent = "▶ Escuchar"; return; }
  document.querySelectorAll(".musica-opcion button[data-sonando]").forEach((b) => { delete b.dataset.sonando; b.textContent = "▶ Escuchar"; });
  boton.textContent = "Cargando…";
  try {
    const audio = await pedirBinario(`/api/musica-audio?pieza=${MUSICA.pieza.id}&indice=${i}`);
    MUSICA.reproductor = new Audio(URL.createObjectURL(audio));
    MUSICA.reproductor.play();
    boton.dataset.sonando = "1";
    boton.textContent = "❚❚ Pausar";
  } catch (e) {
    boton.textContent = "▶ Escuchar";
    aviso(`No se pudo reproducir: ${e.message}`);
  }
}

async function elegirMusica(i) {
  try {
    await api("musica-elegir", { metodo: "POST", cuerpo: { pieza_id: MUSICA.pieza.id, indice: i } });
    $("dialogo-musica").close();
    await cargarMes().catch(() => {});
    aviso(i === null ? "El reel queda sin música." : `Listo: el reel usará la propuesta ${i + 1}. Se oye en «Ver reel» y en la descarga.`);
  } catch (e) {
    aviso(`No se pudo elegir la música: ${e.message}`);
  }
}

$("musica-ninguna").addEventListener("click", () => elegirMusica(null));
$("musica-otra").addEventListener("click", () => abrirMusica(MUSICA.pieza));
$("dialogo-musica").addEventListener("close", () => { clearTimeout(MUSICA.timer); MUSICA.reproductor?.pause(); });

/** Doble clic sobre el texto para editarlo ahí mismo (solo Reini, con la pieza sin aprobar). */
function textoEditable(pieza, campo, nodo) {
  if (!pieza?.id || estado.rol !== "admin") return nodo;
  nodo.classList.add("editable");
  nodo.title = pieza.estado === "generada" ? "Doble clic para editar" : "Para editar, desmarca «Aprobado»";
  nodo.addEventListener("dblclick", () => {
    if (pieza.estado !== "generada") { aviso("Para editar este texto, primero desmarca «Aprobado» en la pieza."); return; }
    estado.editando = `${pieza.id}:${campo}`;
    render();
    const campoEd = $(`editor-${pieza.id}-${campo}`);
    campoEd?.focus();
    campoEd?.select?.();
  });
  return nodo;
}

function editorTexto(pieza, campo, max) {
  // Edición manual de una tarjeta, escena o caption: guarda una versión nueva y la pieza se vuelve a validar.
  const largo = campo === "caption";
  const entrada = el(largo ? "textarea" : "input", { id: `editor-${pieza.id}-${campo}`, clase: "gancho-editor__entrada",
    ...(largo ? { rows: "8" } : { type: "text" }), maxlength: largo ? "5000" : "400", "aria-label": "Nuevo texto" });
  entrada.value = pieza.contenido[campo] || "";
  const cuenta = el("span", { clase: "contador" }, "");
  const contar = () => {
    const n = contarPalabras(entrada.value);
    cuenta.textContent = `${n}/${max} palabras`;
    cuenta.className = `contador${n > max ? " contador--excede" : ""}`;
  };
  entrada.addEventListener("input", contar);
  contar();
  let hecho = false;
  const original = entrada.value;
  const cerrar = () => { if (hecho) return; hecho = true; estado.editando = null; render(); };
  const guardar = () => {
    if (hecho) return;
    hecho = true;
    estado.editando = null;
    if (entrada.value.trim() === original.trim()) { render(); return; }
    accion(pieza.id, () => api("editar-texto", { metodo: "POST", cuerpo: { pieza_id: pieza.id, campo, texto: entrada.value } }))
      .then(() => refrescarMiniaturasDe(pieza));
  };
  entrada.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && (!largo || ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); guardar(); }
    if (ev.key === "Escape") cerrar();
  });
  // Al salir del campo (clic fuera) se guarda solo; los botones se atienden antes con mousedown.
  entrada.addEventListener("blur", () => setTimeout(guardar, 150));
  return el("div", { clase: "gancho-editor" }, entrada, cuenta,
    el("div", { clase: "gancho-acciones" },
      el("button", { clase: "btn btn--primario btn--chico", type: "button", onclick: guardar }, "Guardar"),
      el("button", { clase: "btn btn--texto btn--chico", type: "button", onclick: cerrar }, "Cancelar")));
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
  const detenible = ["generando", "ajustando"].includes(pieza.estado);
  return el("div", { clase: "estado-proceso", role: "status" },
    el("span", { clase: "giro", "aria-hidden": "true" }), textos[pieza.estado] || "Procesando…",
    detenible ? el("button", {
      clase: "btn btn--secundario btn--chico estado-proceso__detener", type: "button",
      title: "Detiene esta generación: la pieza vuelve a su versión anterior (o queda para reintentar)",
      onclick: () => detenerPieza(pieza.id),
    }, "Detener") : null);
}

/** La pieza ya pasó la etapa de quien mira: Reini (textos), Daniela (diseño) o Luís (publicación). */
function contraible(pieza) {
  const ap = pieza.aprobaciones || {};
  if (estado.rol === "diseno") return Boolean(ap.diseno);
  if (estado.rol === "publicacion") return Boolean(ap.publicacion);
  return pieza.estado === "aprobada";
}

function renderPieza(pieza) {
  const enProceso = estado.ocupadas.has(pieza.id) || ["generando", "ajustando"].includes(pieza.estado);
  const bloqueada = enProceso;
  const c = pieza.contenido;
  // Color de fondo según la última etapa aprobada: gris textos (Reini), azul diseño (Daniela), verde publicación (Luís).
  const ap = pieza.aprobaciones || {};
  const etapa = ap.publicacion ? "publicacion" : ap.diseno ? "diseno" : pieza.estado === "aprobada" ? "textos" : "";
  const tarjeta = el("article", { clase: `pieza${pieza.estado === "aprobada" ? " pieza--aprobada" : ""}${etapa ? ` pieza--etapa-${etapa}` : ""}`, "aria-busy": enProceso ? "true" : null },
    renderCabecera(pieza, bloqueada));
  const cuerpo = el("div", { clase: "pieza__cuerpo" });
  if (!c || enProceso || pieza.estado === "error") {
    cuerpo.append(el("p", { clase: "ayuda" }, pieza.pilar));
    cuerpo.append(renderProceso(estado.ocupadas.has(pieza.id) && !["generando", "ajustando"].includes(pieza.estado)
      ? { ...pieza, estado: pieza.contenido ? "ajustando" : "generando" } : pieza));
  } else if (contraible(pieza) && !estado.expandidas.has(pieza.id)) {
    // Pieza aprobada: se muestra contraída (tipo, fecha y aprobaciones en la cabecera, más el gancho).
    const gancho = c[pieza.formato === "Reel" ? "escena_1_gancho" : "slide_1_gancho"] || c.tema_especifico;
    tarjeta.classList.add("pieza--contraida");
    cuerpo.append(el("div", { clase: "pieza__resumen" },
      el("p", { clase: "pieza__gancho" }, gancho),
      el("button", { clase: "btn btn--texto btn--chico", type: "button", "aria-expanded": "false",
        onclick: () => { estado.expandidas.add(pieza.id); render(); } }, "Ver pieza completa ▾")));
  } else {
    cuerpo.append(
      contraible(pieza) ? el("div", { clase: "pieza__plegar" }, el("button", { clase: "btn btn--texto btn--chico", type: "button",
        "aria-expanded": "true", onclick: () => { estado.expandidas.delete(pieza.id); render(); } }, "Contraer ▴")) : null,
      el("div", { clase: "pieza__titulo" }, el("h2", {}, c.tema_especifico), el("p", {}, pieza.pilar)),
      ...renderAlertas(pieza),
      renderInvestigacion(c.investigacion, pieza.id),
      renderTextos(pieza),
      renderCaption(c, pieza),
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

const controles = new Map(); // piezaId → AbortController de la petición en curso

async function procesar(piezaId, ruta) {
  const control = new AbortController();
  controles.set(piezaId, control);
  estado.ocupadas.add(piezaId);
  estado.mensajes[piezaId] = null;
  render();
  try {
    await api(ruta, { metodo: "POST", cuerpo: { pieza_id: piezaId }, senal: control.signal });
  } catch (e) {
    if (!control.signal.aborted) estado.mensajes[piezaId] = e.message;
  } finally {
    controles.delete(piezaId);
    estado.ocupadas.delete(piezaId);
    await cargarMes().catch(() => render());
  }
}

async function detenerPieza(piezaId) {
  estado.detenerLote = true; // si había una generación o unos ajustes en lote, no sigue con las demás piezas
  try {
    await api("detener-pieza", { metodo: "POST", cuerpo: { pieza_id: piezaId } });
  } catch (e) {
    estado.mensajes[piezaId] = `No se pudo detener: ${e.message}`;
  }
  controles.get(piezaId)?.abort();
  await cargarMes().catch(() => render());
}

const generarPieza = (id) => procesar(id, "generar-pieza");

async function generarPendientes() {
  if (estado.generandoTodo) return;
  estado.generandoTodo = true;
  estado.detenerLote = false;
  try {
    for (const pieza of estado.piezas.filter((p) => p.estado === "pendiente")) {
      if (estado.detenerLote) break;
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
  estado.detenerLote = false;
  for (const [i, pieza] of conComentarios.entries()) {
    if (estado.detenerLote) break;
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
  $("tarjetas-contador").textContent = `${$("dialogo-tarjetas").style.getPropertyValue("--rel") < 0.7 ? "Escena" : "Tarjeta"} ${i + 1} de ${n}`;
  $("tarjetas-ant").disabled = i <= 0;
  $("tarjetas-sig").disabled = i >= n - 1;
}

async function cargarVistaTarjetas(piezaId, indice = 0) {
  const { imagenes, relacion, video_escena_1: video } = await api(`tarjetas-vista?pieza=${piezaId}&semilla=${semillaDe(piezaId)}`);
  const posicion = $("dialogo-tarjetas").open ? tarjetaActual() : indice;
  piezaTarjetas = piezaId;
  const pieza = miniaturas.piezas.get(piezaId);
  if (pieza) {  // reutiliza estas imágenes en las miniaturas de la pieza
    miniaturas.cache.set(claveVista(pieza), { imagenes, relacion });
    repintarMiniaturas(piezaId);
  }
  $("dialogo-tarjetas").style.setProperty("--rel", String(relacion));
  $("tarjetas-ayuda").textContent = relacion < 0.7
    ? "9:16 · 1080 × 1920. Un PDF por reel: una página por escena, con el texto en pantalla editable. Ábrelo en Adobe Express con «Empezar con tu contenido». En la escena 1 se ve aquí el ícono animado; el video se descarga desde «Ícono animado de la escena 1»."
    : "4:5 · 1080 × 1350. Los recuadros del ícono (tarjeta 1) y la foto (tarjeta 2) solo se ven aquí: el PDF descargado deja ese espacio libre. «Rehacer» cambia el ícono de línea cuando la tarjeta no pidió uno.";
  $("tarjetas-titulo").textContent = relacion < 0.7 ? "Vista previa del guion visual" : "Vista previa del carrusel";
  $("tarjetas-pista").replaceChildren(...imagenes.map((src, i) => {
    const img = el("img", { src, alt: `${relacion < 0.7 ? "Escena" : "Tarjeta"} ${i + 1} de ${imagenes.length}` });
    if (i !== 0 || !video?.url) return img;
    // Escena 1 del reel: el video del ícono animado se reproduce encima de la imagen, en el lugar del ícono.
    return el("div", { clase: "carrusel__escena" }, img,
      el("video", { src: video.url, autoplay: true, loop: true, muted: true, playsinline: true,
        "aria-label": "Ícono animado de la escena 1",
        style: `left:${video.x * 100}%;top:${video.y * 100}%;width:${video.ancho * 100}%;height:${video.alto * 100}%` }));
  }));
  if (!$("dialogo-tarjetas").open) $("dialogo-tarjetas").showModal();
  $("tarjetas-pista").scrollLeft = posicion * $("tarjetas-pista").clientWidth;
  actualizarCarrusel();
  $("tarjetas-pista").focus();
}

async function verTarjetas(piezaId, boton, indice = 0) {
  const esMiniatura = boton.classList.contains("miniatura");
  boton.disabled = true;
  const texto = boton.textContent;
  if (esMiniatura) boton.classList.add("miniatura--cargando");
  else boton.textContent = "Generando vista previa…";
  try {
    await cargarVistaTarjetas(piezaId, indice);
  } catch (e) {
    aviso(`No se pudo generar la vista previa: ${e.message}`);
  } finally {
    boton.disabled = false;
    if (esMiniatura) boton.classList.remove("miniatura--cargando");
    else boton.textContent = texto;
  }
}

$("tarjetas-rehacer").addEventListener("click", async (ev) => {
  const boton = ev.currentTarget;
  boton.disabled = true;
  boton.textContent = "Rehaciendo…";
  miniaturas.semillas.set(piezaTarjetas, semillaDe(piezaTarjetas) + 1);
  try {
    await cargarVistaTarjetas(piezaTarjetas);
  } catch (e) {
    miniaturas.semillas.set(piezaTarjetas, semillaDe(piezaTarjetas) - 1);
    aviso(`No se pudo rehacer la propuesta: ${e.message}`);
  } finally {
    boton.disabled = false;
    boton.textContent = "Rehacer";
  }
});

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
    await descargarArchivo(`/api/tarjetas-pdf?pieza=${piezaTarjetas}&semilla=${semillaDe(piezaTarjetas)}`, "tarjetas.pdf");
  } catch (e) {
    aviso(`No se pudo descargar el PDF: ${e.message}`);
  } finally {
    boton.disabled = false;
  }
});


// ---------- imágenes de Krea: ícono isométrico (1), foto (2) e ícono de línea (3) ----------

const IMAGEN_TARJETA = {
  1: { boton: "Ícono de la tarjeta 1", titulo: "Ícono isométrico · Tarjeta 1", generar: "Generar íconos", alt: "Ícono generado en Krea",
       ayuda: "Genera en Krea variantes del ícono isométrico de la portada, con el estilo de la guía visual" },
  2: { boton: "Foto de la tarjeta 2", titulo: "Foto · Tarjeta 2", generar: "Generar fotos", alt: "Foto generada en Krea",
       ayuda: "Genera en Krea variantes de la foto realista de la tarjeta 2" },
  3: { boton: "Ícono de la tarjeta 3", titulo: "Ícono de línea · Tarjeta 3", generar: "Generar íconos", alt: "Ícono de línea generado en Krea",
       ayuda: "Genera en Krea variantes del ícono de línea de la tarjeta 3, con el estilo de los íconos de la guía visual" },
};

// Misma regla que el servidor (rc/tarjetas.py · RE_CIFRA): la primera cifra del texto se muestra en grande.
const RE_CIFRA = /[+\-]?(?:US\$|\$)?\d+(?:[.,]\d+)*\s?(?:%|x\b)?/;
const RE_ORDEN = /(?:\b(?:paso|pasos|etapa|fase|step|nivel|punto|tip|consejo|clave|regla|n[°º.]?|no\.|número|numero)\s*#?\s*|#\s*)$/i;

/** ¿El texto tiene una cifra para mostrar en grande? Los números de orden («Paso 1», «1.») no cuentan. */
function tieneCifra(texto) {
  for (const m of texto.matchAll(new RegExp(RE_CIFRA.source, "g"))) {
    if (m.index && /\d/.test(texto[m.index - 1])) continue;
    if (!/\d/.test(m[0])) continue;
    const numero = m[0].trim(), despues = texto.slice(m.index + m[0].length), antes = texto.slice(0, m.index);
    const orden = /^\d{1,2}$/.test(numero) && !/^\s?[-–/]\s?\d/.test(despues)
      && (RE_ORDEN.test(antes.slice(-25)) || (!antes.trim() && /^\s*[.)]/.test(despues)));
    if (!orden) return true;
  }
  return false;
}

/** Cifras que se pueden resaltar (misma regla que rc/tarjetas.py · candidatos_cifra): rangos, números y con unidad. */
function candidatosCifra(texto) {
  const hallados = [];
  for (const m of texto.matchAll(/\d+(?:[.,]\d+)*\s?[-–/]\s?\d+(?:[.,]\d+)*\s?%?/g)) hallados.push([m.index, 0, m[0].trim()]);
  for (const m of texto.matchAll(/(?:US\$|\$)?\d+(?:[.,]\d+)*/g)) {
    hallados.push([m.index, 1, m[0]]);
    const unidad = texto.slice(m.index + m[0].length).match(/^\s?(%|x\b)/);
    if (unidad) hallados.push([m.index, 2, m[0] + unidad[0]]);
  }
  hallados.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return [...new Set(hallados.map((h) => h[2]))];
}

/** Tarjeta o escena donde la cifra va en grande y el texto tiene más de una opción para resaltar. */
function opcionCifra(pieza, n) {
  const campo = CAMPOS[pieza.formato]?.[n - 1]?.campo;
  const enGrande = pieza.formato === "Reel" ? n >= 2 && n <= 4 : n === 4;
  const texto = pieza.contenido?.[campo] || "";
  return enGrande && tieneCifra(texto) && candidatosCifra(texto).length > 1;
}

function selectorCifra(pieza, n, texto) {
  const elegida = pieza.diseno_reel?.cifras?.[String(n)] || "";
  const opciones = candidatosCifra(texto);
  return el("label", { clase: "reel-foto", title: "Qué cifra del texto se muestra en grande" }, "Cifra a resaltar: ",
    el("select", { disabled: pieza.estado === "aprobada",
      onchange: (ev) => accion(pieza.id, () => api("cifra", { metodo: "POST",
        cuerpo: { pieza_id: pieza.id, numero: n, cifra: ev.target.value } })).then(() => refrescarMiniaturasDe(pieza)) },
      el("option", { value: "", selected: !elegida }, `Automática (${opciones[0]})`),
      ...opciones.map((o) => el("option", { value: o, selected: o === elegida }, o))));
}

/** Escenas intermedias del reel sin cifra: si hay dos o más, cualquiera (menos una) puede llevar foto. */
function opcionFoto(pieza, n) {
  if (pieza.formato !== "Reel" || n < 2 || n > 4) return false;
  const sin = [2, 3, 4].filter((k) => !tieneCifra(pieza.contenido?.[CAMPOS.Reel[k - 1].campo] || ""));
  return sin.length >= 2 && sin.includes(n);
}

/** Qué imagen lleva la tarjeta o escena `n` de la pieza (null si no lleva). */
function infoImagen(pieza, n) {
  if (pieza.formato !== "Reel") return IMAGEN_TARJETA[n] || null;
  if (n === 1) return { reel: true, boton: "Ícono animado de la escena 1", titulo: "Ícono isométrico animado · Escena 1",
    generar: "Generar íconos", alt: "Ícono generado en Krea",
    ayuda: "Genera en Krea el ícono isométrico de la escena 1 y su animación corta en video" };
  const texto = pieza.contenido?.[CAMPOS.Reel[n - 1]?.campo] || "";
  if (n > 4 || tieneCifra(texto)) return null; // el cierre no lleva imagen; con cifra, la cifra va en grande
  if ((pieza.diseno_reel?.fotos || []).includes(n)) return { reel: true, boton: `Foto de la escena ${n}`,
    titulo: `Foto · Escena ${n}`, generar: "Generar fotos", alt: "Foto generada en Krea",
    ayuda: `Genera en Krea la foto de apoyo (con velo) de la escena ${n}` };
  return { reel: true, boton: `Ícono de la escena ${n}`, titulo: `Ícono de línea · Escena ${n}`, generar: "Generar íconos",
    alt: "Ícono de línea generado en Krea", ayuda: `Genera en Krea un ícono de línea simple para la escena ${n}, basado en su texto` };
}

const ilus = { pieza: null, tarjeta: 1, items: [], configurado: true, timer: null, enviando: false, mensaje: "",
  sugiriendo: false, previas: [], controlSugerir: null };

function refrescarMiniaturasDe(pieza) {
  miniaturas.rev.set(pieza.id, (miniaturas.rev.get(pieza.id) || 0) + 1);
  repintarMiniaturas(pieza.id);
  pedirMiniaturas(pieza);
}

async function elegirIlustracion(it, elegida) {
  ilus.mensaje = "";
  try {
    await api("ilustracion-elegir", { metodo: "POST", cuerpo: { id: it.id, elegida } });
    refrescarMiniaturasDe(ilus.pieza);
    if (elegida && !(ilus.pieza.formato === "Reel" && ilus.tarjeta === 1)) { $("dialogo-ilustraciones").close(); return; } // elegida: se cierra y se ve en la miniatura
  } catch (e) {
    ilus.mensaje = `No se pudo ${elegida ? "usar" : "quitar"} la imagen: ${e.message}`;
  }
  await cargarIlustraciones();
}

function renderIlustraciones() {
  const hayEnCola = ilus.items.some((it) => it.estado === "en_cola" || it.video_estado === "en_cola");
  const conVideo = ilus.pieza?.formato === "Reel" && ilus.tarjeta === 1;
  const donde = ilus.info?.reel ? "la escena" : "la tarjeta";
  const mensaje = ilus.mensaje || (ilus.configurado ? "" : "Las imágenes aún no están activadas: falta configurar KREA_API_TOKEN en Vercel (ver README).");
  $("ilus-aviso").hidden = !mensaje;
  $("ilus-aviso").textContent = mensaje;
  $("ilus-generar").disabled = ilus.enviando || ilus.sugiriendo || !ilus.configurado;
  $("ilus-generar").textContent = ilus.enviando ? "Enviando a Krea…" : (ilus.items.length ? "Generar más" : ilus.info.generar);
  $("ilus-sugerir").disabled = ilus.enviando;
  $("ilus-sugerir").textContent = ilus.sugiriendo ? "Detener sugerencia" : "Sugerir otra descripción";
  $("ilus-detener").hidden = !hayEnCola;
  $("ilus-borrar").hidden = !ilus.items.some((it) => !it.elegida);
  $("ilus-galeria").replaceChildren(...(ilus.items.length ? ilus.items.map((it) => {
    const lista = it.estado === "lista" && it.url?.startsWith("https://");
    const marco = el("div", {
      clase: `galeria__marco${it.estado === "en_cola" ? " galeria__marco--cargando" : ""}${it.estado === "fallida" ? " galeria__marco--fallida" : ""}`,
      style: `background-color: ${/^#[0-9A-Fa-f]{6}$/.test(it.fondo) ? it.fondo : "#D8D6D2"}; aspect-ratio: ${it.ancho || 4} / ${it.alto || 3}`,
    });
    if (lista) marco.append(el("img", { src: it.url, alt: ilus.info.alt, loading: "lazy" }));
    else if (it.estado === "en_cola") marco.append("Generando en Krea…");
    else marco.append(it.error || "No se pudo generar");
    return el("figure", { clase: `galeria__item${it.elegida ? " galeria__item--elegida" : ""}` }, marco,
      el("figcaption", { clase: "galeria__pie" },
        el("div", { clase: "galeria__acciones" },
          lista && !it.elegida ? el("button", { clase: "btn btn--primario btn--chico", type: "button", onclick: () => elegirIlustracion(it, true) }, `Usar en ${donde}`) : null,
          it.elegida ? el("span", {}, el("strong", {}, `✓ En ${donde}`)) : null,
          it.elegida ? el("button", { clase: "btn btn--texto", type: "button", onclick: () => elegirIlustracion(it, false) }, "Quitar") : null,
          !it.elegida ? el("button", { clase: "btn btn--texto btn--chico", type: "button", title: "Borra esta imagen (y su animación) de la app",
            onclick: () => borrarIlustraciones({ id: it.id }) }, "Borrar") : null,
          !it.elegida && it.video_estado ? el("button", { clase: "btn btn--texto btn--chico", type: "button", title: "Borra solo la animación de esta imagen",
            onclick: () => borrarIlustraciones({ id: it.id, solo_animacion: true }) }, "Borrar animación") : null),
        lista ? el("a", { href: it.url, target: "_blank", rel: "noopener noreferrer" }, "Abrir en Krea") : el("span", {}, `${it.ancho}×${it.alto}`),
        conVideo && lista ? renderVideo(it) : null));
  }) : [el("p", { clase: "ayuda" }, "Aún no hay imágenes para esta tarjeta. Revisa la descripción y pulsa «Generar».")]));
  clearTimeout(ilus.timer);
  if (hayEnCola && $("dialogo-ilustraciones").open) ilus.timer = setTimeout(cargarIlustraciones, 4000);
}

async function borrarIlustraciones(extra = {}) {
  ilus.mensaje = "";
  try {
    await api("ilustraciones-borrar", { metodo: "POST", cuerpo: { pieza_id: ilus.pieza.id, tarjeta: ilus.tarjeta, ...extra } });
  } catch (e) {
    ilus.mensaje = `No se pudo borrar: ${e.message}`;
  }
  await cargarIlustraciones();
}

function renderVideo(it) {
  const animar = (texto) => el("button", { clase: "btn btn--secundario btn--chico", type: "button",
    title: "Krea anima este ícono en un video corto en bucle (consume saldo de Krea)",
    onclick: async () => {
      try { await api("ilustracion-animar", { metodo: "POST", cuerpo: { id: it.id } }); }
      catch (e) { ilus.mensaje = `No se pudo animar: ${e.message}`; }
      await cargarIlustraciones();
    } }, texto);
  if (it.video_estado === "lista" && it.video_url?.startsWith("https://")) {
    return el("div", { clase: "galeria__video" },
      el("video", { src: it.video_url, autoplay: true, loop: true, muted: true, playsinline: true }),
      el("div", { clase: "gancho-acciones" },
        el("a", { href: it.video_url, target: "_blank", rel: "noopener noreferrer", download: "" }, "Descargar video"),
        animar("Regenerar video")));
  }
  if (it.video_estado === "en_cola") return el("p", { clase: "ayuda" }, "Animando en Krea… (1-3 minutos)");
  if (it.video_estado === "fallida") return el("div", { clase: "galeria__video" },
    el("p", { clase: "ayuda" }, it.video_error || "No se pudo animar."), animar("Reintentar animación"));
  return animar("Animar ícono");
}

async function cargarIlustraciones() {
  try {
    const d = await api(`ilustraciones?pieza=${ilus.pieza.id}`);
    ilus.configurado = d.configurado;
    ilus.items = d.items.filter((it) => it.tarjeta === ilus.tarjeta);
  } catch (e) {
    ilus.mensaje = `No se pudieron cargar las imágenes: ${e.message}`;
  }
  renderIlustraciones();
}

async function abrirIlustraciones(pieza, tarjeta, texto) {
  Object.assign(ilus, { pieza, tarjeta, items: [], enviando: false, mensaje: "", sugiriendo: false, previas: [] });
  ilus.info = infoImagen(pieza, tarjeta);
  $("titulo-ilustraciones").textContent = ilus.info.titulo;
  $("ilus-texto").textContent = texto || "—";
  $("ilus-descripcion").value = "";
  renderIlustraciones();
  $("dialogo-ilustraciones").showModal();
  await cargarIlustraciones();
  // Si ya se generaron imágenes, se retoma la última descripción usada; si no, Claude sugiere una en español.
  const usada = ilus.items.find((it) => it.descripcion)?.descripcion;
  if (usada) {
    $("ilus-descripcion").value = usada;
    ilus.previas.push(usada);
  } else {
    await sugerirDescripcion();
  }
}

async function sugerirDescripcion() {
  if (ilus.sugiriendo) { ilus.controlSugerir?.abort(); return; }
  const actual = $("ilus-descripcion").value.trim();
  if (actual && !ilus.previas.includes(actual)) ilus.previas.push(actual);
  ilus.sugiriendo = true;
  ilus.controlSugerir = new AbortController();
  ilus.mensaje = "";
  renderIlustraciones();
  try {
    const r = await api("ilustracion-sugerir", { metodo: "POST", senal: ilus.controlSugerir.signal, cuerpo: {
      pieza_id: ilus.pieza.id, tarjeta: ilus.tarjeta, previas: ilus.previas.slice(-6) } });
    $("ilus-descripcion").value = r.descripcion;
    ilus.previas.push(r.descripcion);
  } catch (e) {
    if (!ilus.controlSugerir.signal.aborted) ilus.mensaje = `No se pudo sugerir una descripción: ${e.message}`;
  }
  ilus.sugiriendo = false;
  ilus.controlSugerir = null;
  renderIlustraciones();
}

$("ilus-sugerir").addEventListener("click", sugerirDescripcion);
$("ilus-borrar").addEventListener("click", () => borrarIlustraciones());
$("ilus-detener").addEventListener("click", async () => {
  $("ilus-detener").disabled = true;
  try {
    await api("ilustraciones-detener", { metodo: "POST", cuerpo: { pieza_id: ilus.pieza.id, tarjeta: ilus.tarjeta } });
  } catch (e) {
    ilus.mensaje = `No se pudo detener: ${e.message}`;
  }
  $("ilus-detener").disabled = false;
  await cargarIlustraciones();
});

$("ilus-generar").addEventListener("click", async () => {
  ilus.enviando = true;
  ilus.mensaje = "";
  renderIlustraciones();
  try {
    const r = await api("ilustraciones", { metodo: "POST", cuerpo: {
      pieza_id: ilus.pieza.id, tarjeta: ilus.tarjeta, semilla: semillaDe(ilus.pieza.id),
      descripcion: $("ilus-descripcion").value.trim(),
    } });
    if (r.descripcion) $("ilus-descripcion").value = r.descripcion;
  } catch (e) {
    ilus.mensaje = `No se pudieron generar las imágenes: ${e.message}`;
  }
  ilus.enviando = false;
  await cargarIlustraciones();
});
$("ilus-cerrar").addEventListener("click", () => $("dialogo-ilustraciones").close());
$("dialogo-ilustraciones").addEventListener("close", () => { clearTimeout(ilus.timer); ilus.controlSugerir?.abort(); });

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
  const listas = repo.piezas.filter((p) => p.publicada_en).length;
  $("resumen-repo").textContent = `${repo.piezas.length} contenidos · ${listas} ${listas === 1 ? "lista" : "listas"} para publicar`
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
    el("td", { clase: "tenue" }, p.historico ? "—" : fechaCorta(p.publicada_en)));
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
        }, `v${v.version} · ${{ generacion: "original", rehacer: "rehecha" }[v.motivo] || v.motivo} · ${fechaCorta(v.creado_en)}`))) : null,
      renderInvestigacion(vista.contenido.investigacion, p.id),
      renderTextos(vista, !version || version.version === p.version),
      renderCaption(vista.contenido));
  }
  const acciones = el("div", { clase: "pieza__controles" },
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
  if (nombre === "configuracion" && estado.rol !== "admin") nombre = "propuestas";  // Configuración: solo Reini
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

// ---------- configuración: fuentes, Teams y conexiones ----------

const cfg = { fuentes: [], recomendadas: [], teamsConfigurado: false, cargada: false };

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
  $("estado-teams").hidden = cfg.teamsConfigurado;
  $("estado-teams").textContent = "El aviso a Teams aún no está activado: falta configurar TEAMS_WEBHOOK_URL en Vercel (ver README).";
}

$("btn-verificar").addEventListener("click", async (ev) => {
  const boton = ev.currentTarget;
  boton.disabled = true;
  $("lista-conexiones").replaceChildren(el("li", { clase: "ayuda" }, "Verificando…"));
  try {
    const d = await api("verificar-conexiones");
    const nombres = { anthropic: "Anthropic (generación de contenido)", krea: "Krea (íconos, fotos, animaciones y música)", teams: "Microsoft Teams (aviso del día 15)" };
    $("lista-conexiones").replaceChildren(...Object.entries(nombres).map(([clave, nombre]) => el("li", { clase: `conexion conexion--${d[clave]?.ok ? "ok" : "falla"}` },
      el("span", { "aria-hidden": "true" }, d[clave]?.ok ? "✓" : "✕"),
      el("strong", {}, nombre), " — ", d[clave]?.detalle || "Sin datos")));
  } catch (e) {
    $("lista-conexiones").replaceChildren(el("li", { clase: "conexion conexion--falla" }, `No se pudo verificar: ${e.message}`));
  } finally {
    boton.disabled = false;
  }
});

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
    Object.assign(cfg, { fuentes: d.fuentes, recomendadas: d.recomendadas, teamsConfigurado: d.teams_configurado, cargada: true });
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
// ---------- login ----------

function mostrar(vista) {
  $("vista-login").hidden = vista !== "login";
  $("vista-app").hidden = vista !== "app";
  $("btn-salir").hidden = vista !== "app";
}

async function entrarApp() {
  try {
    const yo = await api("yo");
    estado.rol = yo.rol || "admin";
    estado.maxCaption = yo.max_palabras_caption || 150;
    document.body.dataset.rol = estado.rol;
  } catch (e) {
    if (e.estado === 401) { Sesion.borrar(); mostrar("login"); return; }
    mostrar("app");
    aviso(`Error: ${e.message}`);
    return;
  }
  mostrar("app");
  try {
    await cargarMes();
    if (estado.rol === "admin" && estado.piezas.some((p) => p.estado === "pendiente")) generarPendientes();
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

// ---------- restablecer contraseña (Supabase Auth: enlace por correo) ----------

function pantallaLogin(cual) {
  // cual: "ingresar" | "recuperar" | "nueva"
  $("form-login").hidden = cual !== "ingresar";
  $("form-recuperar").hidden = cual !== "recuperar";
  $("form-nueva-clave").hidden = cual !== "nueva";
  document.querySelector("#vista-login h1").textContent =
    { ingresar: "Ingresar", recuperar: "Restablecer contraseña", nueva: "Nueva contraseña" }[cual];
  mostrar("login");
}

$("btn-olvide").addEventListener("click", () => {
  $("email-recuperar").value = $("email").value;
  $("recuperar-mensaje").textContent = "";
  pantallaLogin("recuperar");
  $("email-recuperar").focus();
});
$("btn-volver-login").addEventListener("click", () => pantallaLogin("ingresar"));

$("form-recuperar").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const boton = ev.submitter;
  boton.disabled = true;
  const destino = encodeURIComponent(`${location.origin}/`);
  try {
    await fetch(`${config.supabase_url}/auth/v1/recover?redirect_to=${destino}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: config.supabase_anon_key },
      body: JSON.stringify({ email: $("email-recuperar").value.trim() }),
    });
    // Mismo mensaje exista o no la cuenta (no revela qué correos están registrados).
    $("recuperar-mensaje").textContent = "Si ese correo tiene una cuenta, te llegará un enlace en unos minutos. Revisa también la carpeta de spam.";
  } catch {
    $("recuperar-mensaje").textContent = "No se pudo enviar el enlace. Intenta de nuevo.";
  } finally {
    boton.disabled = false;
  }
});

$("form-nueva-clave").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const clave = $("clave-nueva").value;
  $("nueva-clave-error").textContent = "";
  if (clave.length < 8) { $("nueva-clave-error").textContent = "La contraseña debe tener al menos 8 caracteres."; return; }
  if (clave !== $("clave-nueva-2").value) { $("nueva-clave-error").textContent = "Las contraseñas no coinciden."; return; }
  const r = await fetch(`${config.supabase_url}/auth/v1/user`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", apikey: config.supabase_anon_key,
      Authorization: `Bearer ${Sesion.leer()?.access_token || ""}` },
    body: JSON.stringify({ password: clave }),
  });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    $("nueva-clave-error").textContent = datos.msg || datos.error_description || "No se pudo guardar. Pide un enlace nuevo.";
    return;
  }
  $("clave-nueva").value = $("clave-nueva-2").value = "";
  pantallaLogin("ingresar");
  await entrarApp();
});

/** Enlace del correo (restablecer contraseña o invitación): trae la sesión en el fragmento de la URL. */
function leerEnlaceDeCorreo() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ""));
  if (!h.toString()) return null;
  history.replaceState(null, "", location.pathname + location.search);  // no dejar los tokens en la barra
  if (h.get("error") || h.get("error_description")) {
    return { error: "El enlace no es válido o ya venció. Pide uno nuevo con «¿Olvidaste tu contraseña?»." };
  }
  const tipo = h.get("type");
  if (h.get("access_token") && ["recovery", "invite", "signup"].includes(tipo)) {
    Sesion.guardar({ access_token: h.get("access_token"), refresh_token: h.get("refresh_token") });
    return { tipo };
  }
  return null;
}

(async () => {
  try {
    await cargarConfig();
  } catch (e) {
    mostrar("login");
    $("login-error").textContent = e.message;
    return;
  }
  const enlace = leerEnlaceDeCorreo();
  if (enlace?.error) { pantallaLogin("ingresar"); $("login-error").textContent = enlace.error; return; }
  if (enlace) { pantallaLogin("nueva"); $("clave-nueva").focus(); return; }  // crear o cambiar la contraseña
  if (Sesion.leer()) await entrarApp(); else mostrar("login");
})();

// Clic fuera de una ventana (en el fondo oscuro) la cierra.
document.querySelectorAll("dialog").forEach((d) => d.addEventListener("click", (ev) => {
  if (ev.target !== d) return;
  const r = d.getBoundingClientRect();
  const fuera = ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom;
  if (fuera) d.close();
}));

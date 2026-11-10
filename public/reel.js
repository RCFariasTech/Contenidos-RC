"use strict";
// Reel terminado: arma el video de 30 s en el navegador (canvas 1080 x 1920) con las escenas del guion, textos que
// entran animados, el ícono animado de la escena 1 y transiciones elegidas entre escenas; lo graba con MediaRecorder
// y lo descarga. Usa api(), el() y $() de app.js. No graba audio.

const REEL = { datos: null, pieza: null, imagenes: [], video: null, conVideo: false, reproduciendo: false,
  grabador: null, cuadro: 0 };
const TRANSICIONES = [
  ["fundido", "Fundido"], ["deslizar", "Deslizar ←"], ["subir", "Deslizar ↑"], ["zoom", "Zoom"],
  ["barrido", "Barrido"], ["corte", "Corte directo"],
];
const DUR_TRANSICION = 0.6;

const ease = {
  salida: (p) => 1 - Math.pow(1 - p, 3),
  rebote: (p) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
  inOut: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
};
const lim = (v) => Math.max(0, Math.min(1, v));

function clavesTransicion(piezaId) { return `reel-transiciones-${piezaId}`; }

function transicionesGuardadas(piezaId) {
  try {
    const t = JSON.parse(localStorage.getItem(clavesTransicion(piezaId)) || "null");
    if (Array.isArray(t) && t.length === 4) return t;
  } catch { /* sin almacenamiento */ }
  return ["fundido", "deslizar", "zoom", "subir"];
}

function transicionesActuales() {
  return [1, 2, 3, 4].map((i) => $(`reel-trans-${i}`).value);
}

let fuentesCargadas = null;
function cargarFuentes() {
  if (!fuentesCargadas) {
    fuentesCargadas = Promise.all([
      new FontFace("SpaceGrotesk-Bold", "url(/fuentes/SpaceGrotesk-Bold.ttf)").load(),
      new FontFace("Sora-Regular", "url(/fuentes/Sora-Regular.ttf)").load(),
    ]).then((caras) => caras.forEach((c) => document.fonts.add(c)));
  }
  return fuentesCargadas;
}

function cargarImagen(src) {
  return new Promise((ok, mal) => { const i = new Image(); i.onload = () => ok(i); i.onerror = mal; i.src = src; });
}

async function cargarVideoIcono(pieza, url) {
  // 1) Servido por la app (mismo dominio): se ve y además se puede grabar dentro del reel.
  try {
    const r = await fetch(`/api/video-icono?pieza=${pieza.id}`,
      { headers: { Authorization: `Bearer ${Sesion.leer()?.access_token || ""}` } });
    if (r.ok) {
      const v = await cargarVideo(URL.createObjectURL(await r.blob()), false);
      if (v) return { video: v, grabable: true };
    }
  } catch { /* se intenta directo */ }
  // 2) Directo desde Krea: se ve en la vista previa, pero el navegador no deja grabarlo.
  const v = await cargarVideo(url, false);
  return { video: v, grabable: false };
}

function cargarVideo(url, cors = true) {
  return new Promise((ok) => {
    const v = document.createElement("video");
    Object.assign(v, { muted: true, loop: true, playsInline: true, preload: "auto" });
    if (cors) v.crossOrigin = "anonymous";
    v.oncanplaythrough = () => ok(v);
    v.onerror = () => ok(null);
    v.src = url;
    setTimeout(() => ok(v.readyState >= 3 ? v : null), 15000);
  });
}

function duracionTotal() { return REEL.datos.escenas.reduce((s, e) => s + e.duracion, 0); }

// ---------- dibujo ----------

function dibujarTextos(ctx, textos, t) {
  // Cada palabra sube y aparece con un leve rebote, escalonada por renglón y por palabra; la cifra crece y cuenta.
  for (const tx of textos) {
    ctx.fillStyle = tx.color;
    ctx.font = `${tx.tam}px "${tx.fuente}"`;
    ctx.textBaseline = "alphabetic";
    if (tx.rol === "cifra") { dibujarCifra(ctx, tx, t); continue; }
    const palabras = tx.texto.split(" ");
    let x = tx.x;
    palabras.forEach((palabra, j) => {
      const inicio = 0.25 + tx.linea * 0.16 + j * 0.06;
      const p = lim((t - inicio) / 0.5);
      if (p > 0) {
        ctx.save();
        ctx.globalAlpha = lim(p * 1.6);
        ctx.translate(0, (1 - ease.rebote(p)) * tx.tam * 0.6);
        ctx.fillText(palabra, x, tx.y);
        ctx.restore();
      }
      x += ctx.measureText(palabra + " ").width;
    });
  }
}

function dibujarCifra(ctx, tx, t) {
  const p = lim((t - 0.45) / 0.9);
  if (p <= 0) return;
  const m = tx.texto.match(/(\d+(?:[.,]\d+)*)/);
  let texto = tx.texto;
  if (m && p < 1) {
    const decimales = (m[1].split(/[.,]/)[1] || "").length;
    const valor = parseFloat(m[1].replace(/\.(?=\d{3}\b)/g, "").replace(",", ".")) * ease.salida(p);
    let numero = valor.toFixed(decimales);
    if (m[1].includes(",")) numero = numero.replace(".", ",");
    texto = tx.texto.replace(m[1], numero);
  }
  const ancho = ctx.measureText(tx.texto).width;
  const escala = 0.6 + 0.4 * ease.rebote(lim(p * 1.3));
  ctx.save();
  ctx.globalAlpha = lim(p * 2);
  ctx.translate(tx.x + ancho / 2, tx.y - tx.tam * 0.35);
  ctx.scale(escala, escala);
  ctx.fillText(texto, -ancho / 2, tx.tam * 0.35);
  ctx.restore();
}

function quitarFondo(a, lado) {
  // Croma: el fondo del video (muestreado en las esquinas de cada cuadro) se vuelve transparente, con borde suave,
  // para que el ícono quede sobre el color real de la escena sin halo. Lanza error si el video no es del mismo dominio.
  const img = a.getImageData(0, 0, lado, lado), d = img.data;
  const m = Math.max(4, Math.round(lado * 0.02)), muestras = [0, 0, 0];
  let n = 0;
  for (const [x0, y0] of [[0, 0], [lado - m, 0], [0, lado - m], [lado - m, lado - m]]) {
    for (let y = y0; y < y0 + m; y += 2) for (let x = x0; x < x0 + m; x += 2) {
      const k = (y * lado + x) * 4;
      muestras[0] += d[k]; muestras[1] += d[k + 1]; muestras[2] += d[k + 2]; n += 1;
    }
  }
  const [fr, fg, fb] = muestras.map((v) => v / n);
  const t1 = 26, t2 = 80;
  for (let k = 0; k < d.length; k += 4) {
    const dist = Math.abs(d[k] - fr) + Math.abs(d[k + 1] - fg) + Math.abs(d[k + 2] - fb);
    if (dist <= t1) { d[k + 3] = 0; continue; }
    if (dist < t2) d[k + 3] = Math.round(d[k + 3] * (dist - t1) / (t2 - t1));
  }
  a.putImageData(img, 0, 0);
}

function dibujarVideo(ctx) {
  const v = REEL.video, caja = REEL.datos.video_escena_1;
  if (!REEL.conVideo || !v || !caja || v.readyState < 2) return;
  const lado = caja.lado, aux = REEL.aux, a = aux.getContext("2d", { willReadFrequently: true });
  if (aux.width !== lado) aux.width = aux.height = lado;
  a.globalCompositeOperation = "source-over";
  a.clearRect(0, 0, lado, lado);
  a.drawImage(v, 0, 0, lado, lado);
  if (REEL.croma !== false) {
    try { quitarFondo(a, lado); REEL.croma = true; } catch { REEL.croma = false; }
  }
  if (!REEL.croma) {
    // Sin croma (video directo de Krea): bordes difuminados para fundirlo con la escena.
    a.globalCompositeOperation = "destination-in";
    const g = a.createRadialGradient(lado / 2, lado / 2, lado * 0.36, lado / 2, lado / 2, lado / 2);
    g.addColorStop(0, "rgba(0,0,0,1)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    a.fillStyle = g;
    a.fillRect(0, 0, lado, lado);
  }
  ctx.drawImage(aux, caja.x, caja.y);
}

function dibujarEscena(ctx, i, t) {
  const { ancho, alto } = REEL.datos;
  // Escena 1 con video y croma: fondo sin el ícono fijo (si no, se vería el ícono fijo detrás del animado).
  const fondo = i === 0 && REEL.conVideo && REEL.croma === true && REEL.fondoSinIcono ? REEL.fondoSinIcono : REEL.imagenes[i];
  ctx.drawImage(fondo, 0, 0, ancho, alto);
  if (i === 0) dibujarVideo(ctx);
  dibujarTextos(ctx, REEL.datos.escenas[i].textos, t);
}

function dibujarCuadro(ctx, t) {
  const { ancho, alto, escenas } = REEL.datos;
  let inicio = 0, i = 0;
  while (i < escenas.length - 1 && t >= inicio + escenas[i].duracion) { inicio += escenas[i].duracion; i += 1; }
  const local = t - inicio;
  const tipo = i > 0 ? transicionesActuales()[i - 1] : "corte";
  const pT = lim(local / DUR_TRANSICION);
  if (i === 0 || tipo === "corte" || pT >= 1) { dibujarEscena(ctx, i, local); return; }
  // Transición: la escena anterior (en su estado final) y la nueva, compuestas con el efecto elegido.
  const prev = REEL.buf[0], nueva = REEL.buf[1];
  dibujarEscena(prev.getContext("2d"), i - 1, escenas[i - 1].duracion);
  dibujarEscena(nueva.getContext("2d"), i, local);
  const p = ease.inOut(pT);
  ctx.save();
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, ancho, alto);
  if (tipo === "fundido") {
    ctx.drawImage(prev, 0, 0);
    ctx.globalAlpha = p;
    ctx.drawImage(nueva, 0, 0);
  } else if (tipo === "deslizar") {
    ctx.drawImage(prev, -p * ancho, 0);
    ctx.drawImage(nueva, (1 - p) * ancho, 0);
  } else if (tipo === "subir") {
    ctx.drawImage(prev, 0, -p * alto);
    ctx.drawImage(nueva, 0, (1 - p) * alto);
  } else if (tipo === "zoom") {
    ctx.globalAlpha = 1 - p;
    const k1 = 1 + 0.25 * p;
    ctx.drawImage(prev, (ancho - ancho * k1) / 2, (alto - alto * k1) / 2, ancho * k1, alto * k1);
    ctx.globalAlpha = p;
    const k2 = 0.85 + 0.15 * p;
    ctx.drawImage(nueva, (ancho - ancho * k2) / 2, (alto - alto * k2) / 2, ancho * k2, alto * k2);
  } else { // barrido
    ctx.drawImage(prev, 0, 0);
    ctx.beginPath();
    ctx.rect(0, 0, ancho * p, alto);
    ctx.clip();
    ctx.drawImage(nueva, 0, 0);
  }
  ctx.restore();
}

// ---------- reproducción y grabación ----------

function animar(onFin, desde = 0, destino = null) {
  // destino: lienzo de grabación (limpio); se copia cada cuadro a la vista previa.
  const vista = $("reel-lienzo"), lienzo = destino || vista, ctx = lienzo.getContext("2d");
  const total = duracionTotal();
  const t0 = performance.now() - desde * 1000;
  REEL.reproduciendo = true;
  if (REEL.video) { REEL.video.currentTime = 0; REEL.video.play().catch(() => {}); }
  const paso = () => {
    if (!REEL.reproduciendo) return;
    const t = (performance.now() - t0) / 1000;
    dibujarCuadro(ctx, Math.min(t, total - 0.001));
    if (destino) vista.getContext("2d").drawImage(destino, 0, 0);
    $("reel-progreso").value = Math.min(1, t / total);
    if (t >= total) { REEL.reproduciendo = false; onFin?.(); return; }
    REEL.cuadro = requestAnimationFrame(paso);
  };
  paso();
}

function detener() {
  REEL.reproduciendo = false;
  cancelAnimationFrame(REEL.cuadro);
  if (REEL.grabador?.state === "recording") REEL.grabador.stop();
}

function formatoGrabacion() {
  const opciones = ["video/mp4;codecs=avc1.42E01E", "video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
  return opciones.find((m) => window.MediaRecorder?.isTypeSupported?.(m)) || "";
}


function estadoReel(texto) { $("reel-estado").textContent = texto; }

function botonesReel(ocupado) {
  $("reel-reproducir").disabled = ocupado;
  $("reel-descargar").disabled = ocupado;
  $("reel-detener").hidden = !ocupado;
  document.querySelectorAll(".reel-trans select").forEach((s) => { s.disabled = ocupado; });
}

function inicioEscena(i) {
  return REEL.datos.escenas.slice(0, i).reduce((s, e) => s + e.duracion, 0);
}

function reproducir(desde = 0) {
  // Reproduce en bucle hasta que se detenga, se descargue o se cierre la ventana.
  botonesReel(true);
  estadoReel("");
  const vuelta = (d) => animar(() => { if ($("dialogo-reel").open && !REEL.cancelado) vuelta(0); else botonesReel(false); }, d);
  REEL.cancelado = false;
  vuelta(desde);
}

async function descargarReel() {
  REEL.cancelado = true;
  detener();
  const mime = formatoGrabacion();
  if (!mime) { estadoReel("Este navegador no puede grabar video. Usa Chrome o Edge actualizados."); return; }
  // Se graba en un lienzo nuevo (la vista previa pudo quedar «marcada» por el video directo de Krea).
  const rec = Object.assign(document.createElement("canvas"), { width: REEL.datos.ancho, height: REEL.datos.alto });
  REEL.aux = document.createElement("canvas");
  REEL.buf = [0, 1].map(() => Object.assign(document.createElement("canvas"), { width: rec.width, height: rec.height }));
  REEL.conVideo = Boolean(REEL.video && REEL.videoGrabable);
  const avisoVideo = REEL.video && !REEL.videoGrabable
    ? " El ícono animado no se pudo incluir en la grabación (pesa demasiado o Krea no lo permite); se usa el ícono fijo." : "";
  const flujo = rec.captureStream(30);
  const partes = [];
  REEL.grabador = new MediaRecorder(flujo, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
  REEL.grabador.ondataavailable = (ev) => { if (ev.data.size) partes.push(ev.data); };
  REEL.grabador.onstop = () => {
    botonesReel(false);
    if (REEL.cancelado) { estadoReel("Grabación cancelada."); return; }
    const ext = mime.startsWith("video/mp4") ? "mp4" : "webm";
    const archivo = new Blob(partes, { type: mime.split(";")[0] });
    const nombre = `reel-${(REEL.datos.tema || "rc-farias").toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)}.${ext}`;
    const a = el("a", { href: URL.createObjectURL(archivo), download: nombre });
    document.body.append(a);
    a.click();
    a.remove();
    estadoReel(ext === "mp4" ? "Listo: se descargó el MP4." :
      "Listo: se descargó en WebM (este navegador no graba MP4). Para Instagram, conviértelo a MP4 o usa Chrome actualizado.");
  };
  REEL.cancelado = false;
  botonesReel(true);
  estadoReel(`Grabando el reel en tiempo real (${Math.round(duracionTotal())} s). Mantén esta pestaña visible…${avisoVideo}`);
  REEL.grabador.start(500);
  animar(() => { REEL.conVideo = Boolean(REEL.video); setTimeout(() => REEL.grabador.stop(), 200); }, 0, rec);
}

async function abrirReel(pieza, { reproducir: autoplay = false, desde = 0 } = {}) {
  REEL.pieza = pieza;
  REEL.conVideo = true;
  REEL.cancelado = false;
  $("titulo-reel").textContent = "Reel";
  estadoReel("Preparando escenas…");
  botonesReel(true);
  const trans = transicionesGuardadas(pieza.id);
  $("reel-transiciones").replaceChildren(...[1, 2, 3, 4].map((i) => el("label", { clase: "reel-trans" },
    `Escena ${i} → ${i + 1}`,
    el("select", { id: `reel-trans-${i}`, onchange: () => {
      try { localStorage.setItem(clavesTransicion(pieza.id), JSON.stringify(transicionesActuales())); } catch { /* sin almacenamiento */ }
    } }, ...TRANSICIONES.map(([v, t]) => el("option", { value: v, selected: v === trans[i - 1] }, t))))));
  $("dialogo-reel").showModal();
  try {
    const [datos] = await Promise.all([api(`reel-animable?pieza=${pieza.id}`), cargarFuentes()]);
    REEL.datos = datos;
    const lienzo = $("reel-lienzo");
    lienzo.width = datos.ancho;
    lienzo.height = datos.alto;
    REEL.buf = [0, 1].map(() => Object.assign(document.createElement("canvas"), { width: datos.ancho, height: datos.alto }));
    REEL.aux = document.createElement("canvas");
    REEL.imagenes = await Promise.all(datos.escenas.map((e) => cargarImagen(e.fondo)));
    REEL.video = null;
    REEL.videoGrabable = false;
    if (datos.video_escena_1) {
      const r = await cargarVideoIcono(pieza, datos.video_escena_1.url);
      REEL.video = r.video;
      REEL.videoGrabable = r.grabable;
    }
    REEL.conVideo = Boolean(REEL.video);
    REEL.croma = REEL.videoGrabable ? null : false;
    REEL.fondoSinIcono = datos.fondo_escena_1_sin_icono ? await cargarImagen(datos.fondo_escena_1_sin_icono) : null;
    dibujarCuadro(lienzo.getContext("2d"), 1.5);
    botonesReel(false);
    estadoReel(datos.video_escena_1 ? "" : "Aún no hay ícono animado listo para la escena 1: el reel usa el ícono fijo.");
    if (autoplay && $("dialogo-reel").open) reproducir(inicioEscena(Math.min(desde, datos.escenas.length - 1)));
  } catch (e) {
    estadoReel(`No se pudo preparar el reel: ${e.message}`);
  }
}

$("reel-reproducir").addEventListener("click", () => reproducir(0));
$("reel-pdf").addEventListener("click", async (ev) => {
  ev.currentTarget.disabled = true;
  try { await descargarArchivo(`/api/tarjetas-pdf?pieza=${REEL.pieza.id}&semilla=0`, "guion-reel.pdf"); }
  catch (e) { estadoReel(`No se pudo descargar el PDF: ${e.message}`); }
  ev.currentTarget.disabled = false;
});
$("reel-descargar").addEventListener("click", descargarReel);
$("reel-detener").addEventListener("click", () => { REEL.cancelado = true; detener(); botonesReel(false); estadoReel(""); });
$("reel-cerrar").addEventListener("click", () => $("dialogo-reel").close());
$("dialogo-reel").addEventListener("close", () => { REEL.cancelado = true; detener(); REEL.video?.pause(); });
window.abrirReel = abrirReel;

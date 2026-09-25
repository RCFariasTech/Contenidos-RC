"use strict";

// Sesión: tokens de Supabase Auth guardados en localStorage (con try/catch: puede no estar disponible).
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

async function api(ruta, opciones = {}, reintentar = true) {
  const sesion = Sesion.leer();
  const r = await fetch(`/api/${ruta}`, {
    ...opciones,
    headers: { ...(opciones.headers || {}), Authorization: `Bearer ${sesion?.access_token || ""}` },
  });
  if (r.status === 401 && reintentar && sesion?.refresh_token) {
    try {
      await authSupabase("refresh_token", { refresh_token: sesion.refresh_token });
      return api(ruta, opciones, false);
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

function mostrar(vista) {
  document.getElementById("vista-login").hidden = vista !== "login";
  document.getElementById("vista-app").hidden = vista !== "app";
  document.getElementById("btn-salir").hidden = vista !== "app";
}

async function entrarApp() {
  try {
    const yo = await api("yo");
    mostrar("app");
    const n = yo.meses_recientes.length;
    document.getElementById("estado-app").textContent =
      `Sesión de ${yo.email}. Base de datos conectada (${n} mes${n === 1 ? "" : "es"} registrado${n === 1 ? "" : "s"}).`;
  } catch (e) {
    if (e.estado === 401) { Sesion.borrar(); mostrar("login"); return; }
    mostrar("app");
    document.getElementById("estado-app").textContent = `Error: ${e.message}`;
  }
}

document.getElementById("form-login").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const error = document.getElementById("login-error");
  error.textContent = "";
  try {
    await authSupabase("password", {
      email: document.getElementById("email").value.trim(),
      password: document.getElementById("clave").value,
    });
    await entrarApp();
  } catch (e) {
    error.textContent = e.message;
  }
});

document.getElementById("btn-salir").addEventListener("click", () => { Sesion.borrar(); mostrar("login"); });

(async () => {
  try {
    await cargarConfig();
  } catch (e) {
    mostrar("login");
    document.getElementById("login-error").textContent = e.message;
    return;
  }
  if (Sesion.leer()) await entrarApp(); else mostrar("login");
})();

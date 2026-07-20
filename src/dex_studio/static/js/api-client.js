/**
 * Minimal API client — auto-generated endpoint helpers.
 * All functions return Promise<Response>; call .json() or .text() on result.
 */
window.DexAPI = (() => {
  const base = "";

  function headers(extra = {}) {
    const h = { "Content-Type": "application/json", ...extra };
    const csrf = document.querySelector('meta[name="csrf-token"]');
    if (csrf) h["X-CSRF-Token"] = csrf.content;
    return h;
  }

  return {
    get: (path, init) => fetch(base + path, { method: "GET", headers: headers(), ...init }),
    post: (path, body, init) => fetch(base + path, { method: "POST", headers: headers(), body: JSON.stringify(body), ...init }),
    put: (path, body, init) => fetch(base + path, { method: "PUT", headers: headers(), body: JSON.stringify(body), ...init }),
    del: (path, init) => fetch(base + path, { method: "DELETE", headers: headers(), ...init }),
    toast: (msg, kind = "success") => {
      const t = { "show-toast": { msg, kind } };
      document.dispatchEvent(new CustomEvent("htmx:trigger", { detail: t }));
    },
  };
})();
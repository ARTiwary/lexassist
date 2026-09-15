// Default config for local development. Intentionally does NOT set
// window.LEXASSIST_API_BASE, so app.js falls back to
// http://<current hostname>:8000 automatically -- correct when you're
// running the backend locally alongside `python -m http.server`.
//
// On Netlify, this file is regenerated at build time (see build.sh),
// from config.template.js and the API_BASE environment variable set in
// the Netlify dashboard, so the real backend URL never needs to be
// committed here.

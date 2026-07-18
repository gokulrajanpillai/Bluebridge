// Package server hosts the localhost HTTP server: the embedded SPA, the
// /api/v1 REST surface, and the SSE event stream. See REBUILD_PLAN.md §2, §4.
package server

import (
	"encoding/json"
	"io/fs"
	"log/slog"
	"net/http"
	"strings"
)

// Server wires the embedded SPA and the API mux behind the launch-token
// middleware.
type Server struct {
	mux     *http.ServeMux
	version string
	log     *slog.Logger
	auth    AuthBroker
	events  *Hub
}

// Options configures a new Server.
type Options struct {
	WebFS   fs.FS // embedded SPA build output (web/dist)
	Version string
	Token   string // launch token; API routes require it, static assets don't
	Log     *slog.Logger
	Auth    AuthBroker
	Events  *Hub // SSE hub; if nil, /api/v1/events is not registered
}

// New builds the top-level handler: static SPA at "/", API at "/api/v1/*".
func New(opts Options) *Server {
	s := &Server{mux: http.NewServeMux(), version: opts.Version, log: opts.Log, auth: opts.Auth, events: opts.Events}

	api := http.NewServeMux()
	api.HandleFunc("GET /api/v1/version", s.handleVersion)
	api.HandleFunc("GET /api/v1/auth/status", s.handleAuthStatus)
	api.HandleFunc("POST /api/v1/auth/login", s.handleAuthLogin)
	api.HandleFunc("POST /api/v1/auth/logout", s.handleAuthLogout)
	if opts.Events != nil {
		api.HandleFunc("GET /api/v1/events", opts.Events.ServeHTTP)
	}
	// Additional /api/v1/* routes (tenants, resources, pim, ...) are
	// registered here as each milestone lands.

	// /healthz is intentionally public (no launch token) so process managers
	// and smoke tests can probe liveness without the launch secret.
	s.mux.HandleFunc("GET /healthz", s.handleHealth)
	s.mux.Handle("/api/v1/", RequireLaunchToken(opts.Token, api))
	s.mux.Handle("/", spaHandler(opts.WebFS))

	return s
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "version": s.version})
}

// Handler returns the composed http.Handler for use with http.Server.
func (s *Server) Handler() http.Handler {
	return s.mux
}

func (s *Server) handleVersion(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"version": s.version})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// spaHandler serves static assets from fsys, falling back to index.html for
// any path without a matching file so client-side routing works on refresh.
// index.html is served directly (not via http.FileServer) because FileServer
// redirects requests ending in "/index.html" to "./", which would break the
// fallback.
func spaHandler(fsys fs.FS) http.Handler {
	fileServer := http.FileServer(http.FS(fsys))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/")
		if path == "" {
			path = "index.html"
		}
		if _, err := fs.Stat(fsys, path); err != nil {
			serveIndex(w, fsys)
			return
		}
		fileServer.ServeHTTP(w, r)
	})
}

func serveIndex(w http.ResponseWriter, fsys fs.FS) {
	data, err := fs.ReadFile(fsys, "index.html")
	if err != nil {
		http.Error(w, "index.html not found in embedded SPA build", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write(data)
}

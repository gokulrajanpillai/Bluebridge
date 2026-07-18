package server

import (
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/fstest"
)

func testServer(t *testing.T) (*Server, string) {
	t.Helper()
	token, err := NewLaunchToken()
	if err != nil {
		t.Fatalf("NewLaunchToken: %v", err)
	}
	webFS := fstest.MapFS{
		"index.html":     {Data: []byte("<html>spa shell</html>")},
		"assets/app.js":  {Data: []byte("console.log('app')")},
		"assets/app.css": {Data: []byte("body{}")},
	}
	s := New(Options{WebFS: webFS, Version: "test", Token: token, Log: slog.Default()})
	return s, token
}

func TestVersionRequiresToken(t *testing.T) {
	s, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/version", nil)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rec.Code)
	}
}

func TestVersionWithToken(t *testing.T) {
	s, token := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/version", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
}

func TestHealthzIsPublicAndOK(t *testing.T) {
	s, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("healthz should be public and return 200, got %d body=%q", rec.Code, rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("healthz content-type = %q, want application/json", ct)
	}
}

func TestSPAServesIndexAtRoot(t *testing.T) {
	s, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || rec.Body.String() != "<html>spa shell</html>" {
		t.Fatalf("status=%d body=%q", rec.Code, rec.Body.String())
	}
}

func TestSPAFallbackForClientRoutes(t *testing.T) {
	s, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/t/some-tenant/s/some-sub", nil)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || rec.Body.String() != "<html>spa shell</html>" {
		t.Fatalf("expected SPA fallback to index.html, status=%d body=%q", rec.Code, rec.Body.String())
	}
}

func TestSPAServesRealAsset(t *testing.T) {
	s, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/assets/app.js", nil)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || rec.Body.String() != "console.log('app')" {
		t.Fatalf("status=%d body=%q", rec.Code, rec.Body.String())
	}
}

func TestStaticAssetsDoNotRequireToken(t *testing.T) {
	s, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/assets/app.css", nil)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("static asset should not require the launch token, got %d", rec.Code)
	}
}

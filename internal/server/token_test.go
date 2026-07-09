package server

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRequireLaunchToken(t *testing.T) {
	token, err := NewLaunchToken()
	if err != nil {
		t.Fatalf("NewLaunchToken: %v", err)
	}
	if len(token) != 64 {
		t.Fatalf("expected 32-byte hex token (64 chars), got %d", len(token))
	}

	handlerCalled := false
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handlerCalled = true
		w.WriteHeader(http.StatusOK)
	})
	guarded := RequireLaunchToken(token, inner)

	cases := []struct {
		name       string
		authHeader string
		wantStatus int
	}{
		{"missing header", "", http.StatusUnauthorized},
		{"wrong token", "Bearer deadbeef", http.StatusUnauthorized},
		{"correct token", "Bearer " + token, http.StatusOK},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			handlerCalled = false
			req := httptest.NewRequest(http.MethodGet, "/api/v1/tenants", nil)
			if tc.authHeader != "" {
				req.Header.Set("Authorization", tc.authHeader)
			}
			rec := httptest.NewRecorder()
			guarded.ServeHTTP(rec, req)
			if rec.Code != tc.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, tc.wantStatus)
			}
			wantCalled := tc.wantStatus == http.StatusOK
			if handlerCalled != wantCalled {
				t.Errorf("handlerCalled = %v, want %v", handlerCalled, wantCalled)
			}
		})
	}
}

func TestNewLaunchTokenUnique(t *testing.T) {
	a, _ := NewLaunchToken()
	b, _ := NewLaunchToken()
	if a == b {
		t.Fatal("expected two calls to NewLaunchToken to produce different tokens")
	}
}

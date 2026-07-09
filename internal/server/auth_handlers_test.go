package server

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gokulrajanpillai/bluebridge/internal/auth"
)

type fakeBroker struct {
	account    auth.Account
	signedIn   bool
	signInErr  error
	lastMethod auth.Method
	lastTenant string
	signedOut  bool
}

func (f *fakeBroker) SignIn(_ context.Context, tenantID string, method auth.Method) (auth.Account, error) {
	f.lastTenant = tenantID
	f.lastMethod = method
	if f.signInErr != nil {
		return auth.Account{}, f.signInErr
	}
	f.signedIn = true
	return f.account, nil
}

func (f *fakeBroker) Status() (auth.Account, bool) {
	return f.account, f.signedIn
}

func (f *fakeBroker) SignOut() {
	f.signedOut = true
	f.signedIn = false
}

func serverWithAuth(t *testing.T, broker AuthBroker) (*Server, string) {
	t.Helper()
	token, err := NewLaunchToken()
	if err != nil {
		t.Fatalf("NewLaunchToken: %v", err)
	}
	s := New(Options{Auth: broker, Token: token})
	return s, token
}

func TestAuthStatusSignedOut(t *testing.T) {
	s, token := serverWithAuth(t, &fakeBroker{})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/auth/status", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"signedIn":false`) {
		t.Fatalf("expected signedIn:false, got %s", rec.Body.String())
	}
}

func TestAuthLoginSuccess(t *testing.T) {
	broker := &fakeBroker{account: auth.Account{Username: "user@contoso.com", HomeTenantID: "tid-1"}}
	s, token := serverWithAuth(t, broker)

	body := strings.NewReader(`{"tenantId":"tid-1","method":"devicecode"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", body)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
	if broker.lastTenant != "tid-1" || broker.lastMethod != auth.MethodDeviceCode {
		t.Fatalf("broker got tenant=%q method=%q, want tid-1/devicecode", broker.lastTenant, broker.lastMethod)
	}
	if !strings.Contains(rec.Body.String(), "user@contoso.com") {
		t.Fatalf("expected account in response, got %s", rec.Body.String())
	}
}

func TestAuthLoginDefaultsToBrowser(t *testing.T) {
	broker := &fakeBroker{account: auth.Account{Username: "a@b.com"}}
	s, token := serverWithAuth(t, broker)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
	if broker.lastMethod != auth.MethodBrowser {
		t.Fatalf("method = %q, want browser", broker.lastMethod)
	}
}

func TestAuthLoginFailure(t *testing.T) {
	broker := &fakeBroker{signInErr: errors.New("user cancelled")}
	s, token := serverWithAuth(t, broker)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "user cancelled") {
		t.Fatalf("expected error message in body, got %s", rec.Body.String())
	}
}

func TestAuthLogout(t *testing.T) {
	broker := &fakeBroker{signedIn: true}
	s, token := serverWithAuth(t, broker)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/logout", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	s.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want 204", rec.Code)
	}
	if !broker.signedOut {
		t.Fatal("expected SignOut to have been called")
	}
}

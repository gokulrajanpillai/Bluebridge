package azure

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
)

// testClient builds a Client pointed at a mock server with a static token.
func testClient(t *testing.T, h http.Handler) *Client {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	tok := func(_ context.Context, _ string, _ []string) (string, error) { return "test-token", nil }
	return NewClient(tok, WithEndpoint(srv.URL), WithHTTPClient(srv.Client()))
}

func TestGetSendsBearerTokenAndAPIVersion(t *testing.T) {
	var gotAuth, gotAPIVersion string
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		gotAPIVersion = r.URL.Query().Get("api-version")
		w.Write([]byte(`{"value":[]}`))
	}))
	if _, err := c.Tenants(context.Background()); err != nil {
		t.Fatalf("Tenants: %v", err)
	}
	if gotAuth != "Bearer test-token" {
		t.Errorf("Authorization = %q, want Bearer test-token", gotAuth)
	}
	if gotAPIVersion != tenantsAPIVersion {
		t.Errorf("api-version = %q, want %q", gotAPIVersion, tenantsAPIVersion)
	}
}

func TestPaginationFollowsNextLink(t *testing.T) {
	var srvURL string
	mux := http.NewServeMux()
	mux.HandleFunc("/tenants", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("page") == "2" {
			fmt.Fprint(w, `{"value":[{"tenantId":"t2"}]}`)
			return
		}
		fmt.Fprintf(w, `{"value":[{"tenantId":"t1"}],"nextLink":"%s/tenants?api-version=%s&page=2"}`, srvURL, tenantsAPIVersion)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	srvURL = srv.URL
	tok := func(_ context.Context, _ string, _ []string) (string, error) { return "t", nil }
	c := NewClient(tok, WithEndpoint(srv.URL), WithHTTPClient(srv.Client()))

	tenants, err := c.Tenants(context.Background())
	if err != nil {
		t.Fatalf("Tenants: %v", err)
	}
	if len(tenants) != 2 || tenants[0].TenantID != "t1" || tenants[1].TenantID != "t2" {
		t.Fatalf("pagination result = %+v, want t1,t2", tenants)
	}
}

func TestRetriesOn429ThenSucceeds(t *testing.T) {
	var calls int32
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if atomic.AddInt32(&calls, 1) == 1 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"error":{"code":"TooManyRequests","message":"slow down"}}`))
			return
		}
		w.Write([]byte(`{"value":[{"tenantId":"ok"}]}`))
	}))
	tenants, err := c.Tenants(context.Background())
	if err != nil {
		t.Fatalf("expected retry to succeed, got %v", err)
	}
	if len(tenants) != 1 || tenants[0].TenantID != "ok" {
		t.Fatalf("result = %+v", tenants)
	}
	if calls != 2 {
		t.Fatalf("expected 2 calls (1 retry), got %d", calls)
	}
}

func TestForbiddenReturnsTypedRoleHint(t *testing.T) {
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error":{"code":"AuthorizationFailed","message":"denied"}}`))
	}))
	_, err := c.Tenants(context.Background())
	apiErr, ok := err.(*APIError)
	if !ok {
		t.Fatalf("error type = %T, want *APIError", err)
	}
	if !apiErr.IsForbidden() {
		t.Errorf("IsForbidden = false, want true")
	}
	if apiErr.AzureCode != "AuthorizationFailed" {
		t.Errorf("AzureCode = %q", apiErr.AzureCode)
	}
	if apiErr.RoleHint == "" {
		t.Errorf("expected a role hint on 403")
	}
}

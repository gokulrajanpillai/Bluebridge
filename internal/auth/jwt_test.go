package auth

import (
	"encoding/base64"
	"encoding/json"
	"testing"
)

func fakeJWT(t *testing.T, claims map[string]any) string {
	t.Helper()
	payload, err := json.Marshal(claims)
	if err != nil {
		t.Fatalf("marshal claims: %v", err)
	}
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"none"}`))
	body := base64.RawURLEncoding.EncodeToString(payload)
	return header + "." + body + ".sig"
}

func TestParseIDTokenClaimsPreferredUsername(t *testing.T) {
	token := fakeJWT(t, map[string]any{
		"preferred_username": "user@contoso.com",
		"name":                "Test User",
		"tid":                 "tid-123",
	})
	claims, err := parseIDTokenClaims(token)
	if err != nil {
		t.Fatalf("parseIDTokenClaims: %v", err)
	}
	if claims.PreferredUsername != "user@contoso.com" || claims.Name != "Test User" || claims.TenantID != "tid-123" {
		t.Fatalf("got %+v", claims)
	}
}

func TestParseIDTokenClaimsFallsBackToUPN(t *testing.T) {
	token := fakeJWT(t, map[string]any{"upn": "upn-user@contoso.com"})
	claims, err := parseIDTokenClaims(token)
	if err != nil {
		t.Fatalf("parseIDTokenClaims: %v", err)
	}
	if claims.PreferredUsername != "upn-user@contoso.com" {
		t.Fatalf("PreferredUsername = %q, want upn fallback", claims.PreferredUsername)
	}
}

func TestParseIDTokenClaimsFallsBackToUniqueName(t *testing.T) {
	token := fakeJWT(t, map[string]any{"unique_name": "unique-user@contoso.com"})
	claims, err := parseIDTokenClaims(token)
	if err != nil {
		t.Fatalf("parseIDTokenClaims: %v", err)
	}
	if claims.PreferredUsername != "unique-user@contoso.com" {
		t.Fatalf("PreferredUsername = %q, want unique_name fallback", claims.PreferredUsername)
	}
}

func TestParseIDTokenClaimsRejectsMalformedToken(t *testing.T) {
	if _, err := parseIDTokenClaims("not-a-jwt"); err == nil {
		t.Fatal("expected error for malformed token")
	}
}

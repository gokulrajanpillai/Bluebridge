package auth

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
)

type idTokenClaims struct {
	PreferredUsername string `json:"preferred_username"`
	UPN               string `json:"upn"`
	UniqueName        string `json:"unique_name"`
	Name              string `json:"name"`
	TenantID          string `json:"tid"`
}

// parseIDTokenClaims extracts display claims from a JWT's payload without
// verifying its signature. This is only used to populate UI display fields
// (username/name/tenant) immediately after our own credential mints the
// token; it must never be used for authorization decisions.
func parseIDTokenClaims(token string) (idTokenClaims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return idTokenClaims{}, errors.New("not a JWT")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return idTokenClaims{}, err
	}
	var claims idTokenClaims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return idTokenClaims{}, err
	}
	if claims.PreferredUsername == "" {
		if claims.UPN != "" {
			claims.PreferredUsername = claims.UPN
		} else {
			claims.PreferredUsername = claims.UniqueName
		}
	}
	return claims, nil
}

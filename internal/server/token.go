package server

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"net/http"
)

// NewLaunchToken generates a random per-launch bearer token used to lock the
// local API to the SPA instance this process served. See REBUILD_PLAN.md §A2.
func NewLaunchToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

// RequireLaunchToken wraps next, rejecting any request whose bearer token
// does not match token in constant time.
func RequireLaunchToken(token string, next http.Handler) http.Handler {
	want := []byte("Bearer " + token)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got := []byte(r.Header.Get("Authorization"))
		if len(got) != len(want) || subtle.ConstantTimeCompare(got, want) != 1 {
			http.Error(w, `{"error":{"code":"unauthorized","message":"missing or invalid local session token"}}`, http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

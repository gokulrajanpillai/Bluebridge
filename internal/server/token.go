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

// RequireLaunchToken wraps next, rejecting any request that doesn't present
// token, either as an "Authorization: Bearer <token>" header (used by the
// fetch-based API client) or a "?token=" query parameter (the only option
// for the browser EventSource API, which cannot set headers — used solely
// by the /events SSE endpoint).
func RequireLaunchToken(token string, next http.Handler) http.Handler {
	wantHeader := []byte("Bearer " + token)
	wantQuery := []byte(token)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		header := []byte(r.Header.Get("Authorization"))
		query := []byte(r.URL.Query().Get("token"))

		headerOK := len(header) == len(wantHeader) && subtle.ConstantTimeCompare(header, wantHeader) == 1
		queryOK := len(query) > 0 && len(query) == len(wantQuery) && subtle.ConstantTimeCompare(query, wantQuery) == 1

		if !headerOK && !queryOK {
			http.Error(w, `{"error":{"code":"unauthorized","message":"missing or invalid local session token"}}`, http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

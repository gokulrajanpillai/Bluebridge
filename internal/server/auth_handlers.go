package server

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/gokulrajanpillai/bluebridge/internal/auth"
)

// AuthBroker is the subset of auth.Broker the server depends on. Declaring
// it here (rather than depending on the concrete type) keeps this package
// easy to test with a fake.
type AuthBroker interface {
	SignIn(ctx context.Context, tenantID string, method auth.Method) (auth.Account, error)
	Status() (auth.Account, bool)
	SignOut()
}

type authStatusResponse struct {
	SignedIn bool         `json:"signedIn"`
	Account  auth.Account `json:"account,omitempty"`
}

type authLoginRequest struct {
	TenantID string `json:"tenantId"`
	Method   string `json:"method"`
}

func (s *Server) handleAuthStatus(w http.ResponseWriter, r *http.Request) {
	account, signedIn := s.auth.Status()
	writeJSON(w, http.StatusOK, authStatusResponse{SignedIn: signedIn, Account: account})
}

func (s *Server) handleAuthLogin(w http.ResponseWriter, r *http.Request) {
	var req authLoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil && r.ContentLength != 0 {
		writeError(w, http.StatusBadRequest, "invalid_request", "malformed JSON body")
		return
	}

	method := auth.Method(req.Method)
	if method == "" {
		method = auth.MethodBrowser
	}

	account, err := s.auth.SignIn(r.Context(), req.TenantID, method)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "sign_in_failed", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, authStatusResponse{SignedIn: true, Account: account})
}

func (s *Server) handleAuthLogout(w http.ResponseWriter, r *http.Request) {
	s.auth.SignOut()
	w.WriteHeader(http.StatusNoContent)
}

type apiError struct {
	Code     string `json:"code"`
	Message  string `json:"message"`
	RoleHint string `json:"roleHint,omitempty"`
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]apiError{"error": {Code: code, Message: message}})
}

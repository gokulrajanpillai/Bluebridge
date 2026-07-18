package auth

import (
	"context"
	"sync"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
)

// TenantTokens vends access tokens per tenant, lazily creating (and caching)
// one credential per tenant using a single sign-in method. All credentials
// share the same persistent cache, so switching tenants does not force a
// fresh interactive prompt once the user has authenticated. It satisfies the
// azure.TokenFunc contract via its Token method.
//
// See REBUILD_PLAN.md §2 (A1): "Tokens are always requested per tenant."
type TenantTokens struct {
	method Method
	store  azidentity.Cache

	mu    sync.Mutex
	creds map[string]azcore.TokenCredential
}

// NewTenantTokens builds a per-tenant token provider using method for sign-in
// and store as the shared persistent cache (zero value for in-memory only).
func NewTenantTokens(method Method, store azidentity.Cache) *TenantTokens {
	if method == "" {
		method = MethodBrowser
	}
	return &TenantTokens{method: method, store: store, creds: map[string]azcore.TokenCredential{}}
}

// credFor returns (creating if needed) the credential for tenantID.
func (t *TenantTokens) credFor(tenantID string) (azcore.TokenCredential, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if c, ok := t.creds[tenantID]; ok {
		return c, nil
	}
	b := &Broker{cacheStore: t.store}
	cred, err := b.newCredential(tenantID, t.method)
	if err != nil {
		return nil, err
	}
	t.creds[tenantID] = cred
	return cred, nil
}

// Token implements azure.TokenFunc: return a bearer token for tenantID+scopes.
func (t *TenantTokens) Token(ctx context.Context, tenantID string, scopes []string) (string, error) {
	cred, err := t.credFor(tenantID)
	if err != nil {
		return "", err
	}
	res, err := cred.GetToken(ctx, policy.TokenRequestOptions{Scopes: scopes})
	if err != nil {
		return "", err
	}
	return res.Token, nil
}

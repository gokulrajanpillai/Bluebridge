// Package auth manages Azure sign-in: the credential chain (interactive
// browser -> device code -> optional Azure CLI reuse), a persistent
// encrypted token cache, and a small per-process broker that the rest of the
// app queries for tokens. See REBUILD_PLAN.md §2 (A1) and §5.
package auth

import (
	"context"
	"errors"
	"fmt"
	"sync"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
)

// azureCLIClientID is the well-known first-party public client ID used by
// the Azure CLI. Using it means BlueBridge needs no Entra app registration
// of its own — see REBUILD_PLAN.md §2 (A1.1).
const azureCLIClientID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

// Method identifies how the user wants to sign in.
type Method string

const (
	MethodBrowser    Method = "browser"
	MethodDeviceCode Method = "devicecode"
	MethodAzureCLI   Method = "azurecli"
)

// Account is the signed-in identity, derived from the ID token claims.
type Account struct {
	Username     string `json:"username"`
	Name         string `json:"name"`
	HomeTenantID string `json:"homeTenantId"`
}

// DeviceCodePrompt carries the code and URL the user must visit; delivered
// to callers so it can be pushed to the UI over SSE.
type DeviceCodePrompt struct {
	UserCode        string `json:"userCode"`
	VerificationURL string `json:"verificationUrl"`
	Message         string `json:"message"`
}

// Broker holds the current credential and signed-in account for the
// process. It is safe for concurrent use.
type Broker struct {
	mu         sync.RWMutex
	cred       azcore.TokenCredential
	account    Account
	signedIn   bool
	cacheStore azidentity.Cache

	// onDeviceCode, if set, is invoked with the prompt whenever the device
	// code flow needs the user to act. Wired to the SSE hub by the server.
	onDeviceCode func(DeviceCodePrompt)
}

// New creates a Broker. cacheStore may be nil to disable persistence (tokens
// are still cached in-memory for the life of the process by the underlying
// azidentity credentials).
func New(cacheStore azidentity.Cache) *Broker {
	return &Broker{cacheStore: cacheStore}
}

// OnDeviceCode registers a callback fired with the user code/URL each time a
// device-code sign-in is started.
func (b *Broker) OnDeviceCode(fn func(DeviceCodePrompt)) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.onDeviceCode = fn
}

// SignIn establishes a credential for tenantID using method, forces an
// initial token acquisition (so failures surface immediately), and derives
// the account from the result.
func (b *Broker) SignIn(ctx context.Context, tenantID string, method Method) (Account, error) {
	cred, err := b.newCredential(tenantID, method)
	if err != nil {
		return Account{}, err
	}

	res, err := cred.GetToken(ctx, policy.TokenRequestOptions{
		Scopes: []string{"https://management.azure.com/.default"},
	})
	if err != nil {
		return Account{}, fmt.Errorf("sign-in failed: %w", err)
	}

	account := accountFromToken(res)

	b.mu.Lock()
	b.cred = cred
	b.account = account
	b.signedIn = true
	b.mu.Unlock()

	return account, nil
}

func (b *Broker) newCredential(tenantID string, method Method) (azcore.TokenCredential, error) {
	switch method {
	case MethodDeviceCode:
		return azidentity.NewDeviceCodeCredential(&azidentity.DeviceCodeCredentialOptions{
			ClientID: azureCLIClientID,
			TenantID: tenantID,
			Cache:    b.cacheStore,
			UserPrompt: func(_ context.Context, msg azidentity.DeviceCodeMessage) error {
				b.mu.RLock()
				cb := b.onDeviceCode
				b.mu.RUnlock()
				if cb != nil {
					cb(DeviceCodePrompt{
						UserCode:        msg.UserCode,
						VerificationURL: msg.VerificationURL,
						Message:         msg.Message,
					})
				}
				return nil
			},
		})
	case MethodAzureCLI:
		opts := &azidentity.AzureCLICredentialOptions{}
		if tenantID != "" {
			opts.TenantID = tenantID
		}
		return azidentity.NewAzureCLICredential(opts)
	case MethodBrowser, "":
		return azidentity.NewInteractiveBrowserCredential(&azidentity.InteractiveBrowserCredentialOptions{
			ClientID: azureCLIClientID,
			TenantID: tenantID,
			Cache:    b.cacheStore,
		})
	default:
		return nil, fmt.Errorf("unknown sign-in method %q", method)
	}
}

// Status returns the current account and whether a sign-in is active.
func (b *Broker) Status() (Account, bool) {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.account, b.signedIn
}

// Token returns a bearer token for scopes, using the active credential.
func (b *Broker) Token(ctx context.Context, scopes []string) (string, error) {
	b.mu.RLock()
	cred := b.cred
	b.mu.RUnlock()

	if cred == nil {
		return "", errors.New("not signed in")
	}
	res, err := cred.GetToken(ctx, policy.TokenRequestOptions{Scopes: scopes})
	if err != nil {
		return "", err
	}
	return res.Token, nil
}

// SignOut clears the in-process credential and account. The persistent
// cache store (if any) is cleared by the caller, since only it knows the
// on-disk location.
func (b *Broker) SignOut() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.cred = nil
	b.account = Account{}
	b.signedIn = false
}

func accountFromToken(res azcore.AccessToken) Account {
	claims, err := parseIDTokenClaims(res.Token)
	if err != nil {
		return Account{}
	}
	return Account{
		Username:     claims.PreferredUsername,
		Name:         claims.Name,
		HomeTenantID: claims.TenantID,
	}
}

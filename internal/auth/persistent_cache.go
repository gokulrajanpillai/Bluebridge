package auth

import (
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity/cache"
)

// NewPersistentCache opens the OS-native encrypted token cache (DPAPI on
// Windows, Keychain on macOS, kernel keyring/libsecret on Linux) so sign-in
// survives process restarts. Returns nil, err if the OS facility is
// unavailable; callers should fall back to session-only (in-memory) auth
// rather than fail to start.
func NewPersistentCache() (azidentity.Cache, error) {
	return cache.New(nil)
}

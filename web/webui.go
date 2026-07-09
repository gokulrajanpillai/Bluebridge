// Package webui embeds the built React SPA (dist/) into the binary.
//
// dist ships a placeholder index.html in version control so `go build` and
// `go vet` succeed on a fresh checkout without Node installed; `make web`
// (run before `make build`) overwrites it with the real Vite build output.
package webui

import (
	"embed"
	"io/fs"
)

//go:embed dist
var distFS embed.FS

// FS returns the embedded SPA build rooted at dist/ (i.e. index.html is at
// the FS root, not under a "dist/" prefix).
func FS() fs.FS {
	sub, err := fs.Sub(distFS, "dist")
	if err != nil {
		// distFS is a compile-time embed; "dist" always exists.
		panic(err)
	}
	return sub
}

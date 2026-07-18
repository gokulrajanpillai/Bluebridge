// Command bluebridge-cli is the interactive terminal client for BlueBridge:
// sign in, browse tenants and subscriptions, and multi-activate eligible PIM
// roles without leaving the shell. It shares the internal/azure service core
// with the localhost web server.
package main

import (
	"os"

	"github.com/gokulrajanpillai/bluebridge/internal/cli"
)

// version is set at build time via -ldflags "-X main.version=...".
var version = "dev"

func main() {
	os.Exit(cli.Run(os.Args[1:], version, os.Stdout, os.Stderr))
}

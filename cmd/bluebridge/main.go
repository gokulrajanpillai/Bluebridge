// Command bluebridge starts the local BlueBridge server and opens the
// user's default browser to it. See REBUILD_PLAN.md §2, §8.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"syscall"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/gokulrajanpillai/bluebridge/internal/auth"
	"github.com/gokulrajanpillai/bluebridge/internal/logging"
	"github.com/gokulrajanpillai/bluebridge/internal/server"
	webui "github.com/gokulrajanpillai/bluebridge/web"
)

// version is set at build time via -ldflags "-X main.version=...".
var version = "dev"

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	fs := flag.NewFlagSet("bluebridge", flag.ContinueOnError)
	port := fs.Int("port", 0, "port to listen on (0 = pick a free port)")
	noBrowser := fs.Bool("no-browser", false, "do not open the system browser on start")
	tenant := fs.String("tenant", "", "tenant ID to sign in to on start")
	verbose := fs.Bool("verbose", false, "mirror logs to stderr in addition to the log file")
	showVersion := fs.Bool("version", false, "print version and exit")
	if err := fs.Parse(args); err != nil {
		return 2
	}

	if *showVersion {
		fmt.Println(version)
		return 0
	}

	log, closeLog := setupLogger(*verbose)
	defer closeLog()

	ln, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", *port))
	if err != nil {
		log.Error("failed to bind local port", "error", err)
		return 1
	}
	defer ln.Close()

	token, err := server.NewLaunchToken()
	if err != nil {
		log.Error("failed to generate launch token", "error", err)
		return 1
	}

	var persistentCache azidentity.Cache
	if c, err := auth.NewPersistentCache(); err != nil {
		log.Warn("persistent token cache unavailable; sign-in will not survive restart", "error", err)
	} else {
		persistentCache = c
	}
	broker := auth.New(persistentCache)

	events := server.NewHub()
	broker.OnDeviceCode(func(p auth.DeviceCodePrompt) {
		events.Broadcast(server.Event{Name: "auth.devicecode", Data: p})
	})

	srv := server.New(server.Options{
		WebFS:   webui.FS(),
		Version: version,
		Token:   token,
		Log:     log,
		Auth:    broker,
		Events:  events,
	})

	httpServer := &http.Server{Handler: srv.Handler()}

	addr := ln.Addr().(*net.TCPAddr)
	url := fmt.Sprintf("http://127.0.0.1:%d/#token=%s", addr.Port, token)
	if *tenant != "" {
		url += "&tenant=" + *tenant
	}

	errCh := make(chan error, 1)
	go func() {
		errCh <- httpServer.Serve(ln)
	}()

	log.Info("bluebridge listening", "port", addr.Port, "version", version)

	if !*noBrowser {
		if err := openBrowser(url); err != nil {
			log.Warn("could not open system browser automatically", "error", err, "url", url)
			fmt.Fprintf(os.Stderr, "Open this URL in your browser:\n%s\n", url)
		}
	} else {
		fmt.Fprintf(os.Stderr, "BlueBridge is running. Open this URL in your browser:\n%s\n", url)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	select {
	case <-ctx.Done():
		log.Info("shutting down")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(shutdownCtx)
		return 0
	case err := <-errCh:
		if err != nil && err != http.ErrServerClosed {
			log.Error("server error", "error", err)
			return 1
		}
		return 0
	}
}

func setupLogger(verbose bool) (*slog.Logger, func()) {
	logPath := filepath.Join(configDir(), "bluebridge.log")
	rw, err := logging.NewRotatingWriter(logPath, 10*1024*1024, 3)

	var writer io.Writer
	closeFn := func() {}
	if err != nil {
		// Fall back to stderr-only logging rather than fail to start.
		writer = os.Stderr
	} else {
		closeFn = func() { _ = rw.Close() }
		if verbose {
			writer = io.MultiWriter(rw, os.Stderr)
		} else {
			writer = rw
		}
	}

	handler := slog.NewJSONHandler(writer, nil)
	return slog.New(handler), closeFn
}

// configDir returns the OS-appropriate per-user config directory for
// BlueBridge, creating it if necessary.
func configDir() string {
	base, err := os.UserConfigDir()
	if err != nil {
		base = os.TempDir()
	}
	dir := filepath.Join(base, "BlueBridge")
	_ = os.MkdirAll(dir, 0o755)
	return dir
}

func openBrowser(url string) error {
	switch runtime.GOOS {
	case "darwin":
		return exec.Command("open", url).Start()
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
	default:
		return exec.Command("xdg-open", url).Start()
	}
}

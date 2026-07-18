VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS := -s -w -X main.version=$(VERSION)

.PHONY: web build build-cli run test lint vet clean dist

web:
	cd web && npm ci && npm run build

build: web
	go build -ldflags "$(LDFLAGS)" -o bluebridge ./cmd/bluebridge

# The CLI has no embedded SPA, so it does not depend on the web build.
build-cli:
	go build -ldflags "$(LDFLAGS)" -o bluebridge-cli ./cmd/bluebridge-cli

run: build
	./bluebridge

test:
	go test ./...
	cd web && npm run build

lint:
	go vet ./...
	cd web && npm run lint

vet:
	go vet ./...

clean:
	rm -rf bluebridge bluebridge-cli dist web/dist

# Cross-compiles the cgo-free targets (Windows, Linux) into dist/. Run
# `make web` first. macOS Keychain persistence needs cgo (see
# internal/auth/persistent_cache.go), so darwin binaries must be built
# natively on macOS via `make dist-darwin`, not cross-compiled from here.
dist: web
	mkdir -p dist
	GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-windows-amd64.exe ./cmd/bluebridge
	GOOS=windows GOARCH=arm64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-windows-arm64.exe ./cmd/bluebridge
	GOOS=linux   GOARCH=amd64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-linux-amd64 ./cmd/bluebridge
	GOOS=linux   GOARCH=arm64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-linux-arm64 ./cmd/bluebridge
	GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-cli-windows-amd64.exe ./cmd/bluebridge-cli
	GOOS=windows GOARCH=arm64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-cli-windows-arm64.exe ./cmd/bluebridge-cli
	GOOS=linux   GOARCH=amd64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-cli-linux-amd64 ./cmd/bluebridge-cli
	GOOS=linux   GOARCH=arm64 CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-cli-linux-arm64 ./cmd/bluebridge-cli

# Run on a macOS host (native per-arch, cgo enabled for Keychain access).
dist-darwin: web
	mkdir -p dist
	GOARCH=amd64 CGO_ENABLED=1 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-darwin-amd64 ./cmd/bluebridge
	GOARCH=arm64 CGO_ENABLED=1 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-darwin-arm64 ./cmd/bluebridge
	GOARCH=amd64 CGO_ENABLED=1 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-cli-darwin-amd64 ./cmd/bluebridge-cli
	GOARCH=arm64 CGO_ENABLED=1 go build -ldflags "$(LDFLAGS)" -o dist/bluebridge-cli-darwin-arm64 ./cmd/bluebridge-cli

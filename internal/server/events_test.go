package server

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// syncRecorder is an http.ResponseWriter+Flusher safe for concurrent
// writes (from the handler goroutine) and reads (from the test goroutine),
// unlike httptest.ResponseRecorder whose Body is an unsynchronized buffer.
type syncRecorder struct {
	mu   sync.Mutex
	buf  bytes.Buffer
	code int
}

func (s *syncRecorder) Header() http.Header { return http.Header{} }

func (s *syncRecorder) Write(p []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.buf.Write(p)
}

func (s *syncRecorder) WriteHeader(code int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.code = code
}

func (s *syncRecorder) Flush() {}

func (s *syncRecorder) String() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.buf.String()
}

func TestHubBroadcastsToConnectedClient(t *testing.T) {
	hub := NewHub()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/events", nil).WithContext(ctx)
	rec := &syncRecorder{}

	done := make(chan struct{})
	go func() {
		hub.ServeHTTP(rec, req)
		close(done)
	}()

	// Give the handler a moment to subscribe before we broadcast.
	deadline := time.Now().Add(time.Second)
	for {
		hub.mu.Lock()
		n := len(hub.clients)
		hub.mu.Unlock()
		if n == 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for subscriber")
		}
		time.Sleep(time.Millisecond)
	}

	hub.Broadcast(Event{Name: "pim.status", Data: map[string]string{"state": "Provisioned"}})

	deadline = time.Now().Add(time.Second)
	for {
		if strings.Contains(rec.String(), "event: pim.status") {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("timed out waiting for event in body: %q", rec.String())
		}
		time.Sleep(time.Millisecond)
	}

	cancel()
	<-done

	body := rec.String()
	if !strings.Contains(body, "event: pim.status") {
		t.Fatalf("body missing event name: %q", body)
	}
	if !strings.Contains(body, `"state":"Provisioned"`) {
		t.Fatalf("body missing event data: %q", body)
	}
}

func TestHubUnsubscribesOnDisconnect(t *testing.T) {
	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	req := httptest.NewRequest(http.MethodGet, "/api/v1/events", nil).WithContext(ctx)
	rec := &syncRecorder{}

	done := make(chan struct{})
	go func() {
		hub.ServeHTTP(rec, req)
		close(done)
	}()

	deadline := time.Now().Add(time.Second)
	for {
		hub.mu.Lock()
		n := len(hub.clients)
		hub.mu.Unlock()
		if n == 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("timed out waiting for subscriber")
		}
		time.Sleep(time.Millisecond)
	}

	cancel()
	<-done

	hub.mu.Lock()
	n := len(hub.clients)
	hub.mu.Unlock()
	if n != 0 {
		t.Fatalf("expected 0 clients after disconnect, got %d", n)
	}
}

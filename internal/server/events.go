package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
)

// Event is a message pushed to all connected SSE clients. See
// REBUILD_PLAN.md §A4 (server pushes, client doesn't poll blindly).
type Event struct {
	Name string
	Data any
}

// Hub fans Events out to any number of connected SSE clients.
type Hub struct {
	mu      sync.Mutex
	clients map[chan Event]struct{}
}

// NewHub creates an empty Hub.
func NewHub() *Hub {
	return &Hub{clients: make(map[chan Event]struct{})}
}

// Broadcast sends ev to every currently-connected client. Non-blocking:
// slow/stuck clients are skipped rather than backpressuring the sender.
func (h *Hub) Broadcast(ev Event) {
	h.mu.Lock()
	defer h.mu.Unlock()
	for ch := range h.clients {
		select {
		case ch <- ev:
		default:
		}
	}
}

func (h *Hub) subscribe() chan Event {
	ch := make(chan Event, 16)
	h.mu.Lock()
	h.clients[ch] = struct{}{}
	h.mu.Unlock()
	return ch
}

func (h *Hub) unsubscribe(ch chan Event) {
	h.mu.Lock()
	delete(h.clients, ch)
	h.mu.Unlock()
	close(ch)
}

// ServeHTTP implements the /api/v1/events SSE endpoint.
func (h *Hub) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)
	flusher.Flush()

	ch := h.subscribe()
	defer h.unsubscribe(ch)

	for {
		select {
		case <-r.Context().Done():
			return
		case ev := <-ch:
			payload, err := json.Marshal(ev.Data)
			if err != nil {
				continue
			}
			fmt.Fprintf(w, "event: %s\ndata: %s\n\n", ev.Name, payload)
			flusher.Flush()
		}
	}
}

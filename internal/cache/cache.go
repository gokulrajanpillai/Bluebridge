// Package cache provides a generic TTL cache with stale-while-revalidate semantics.
package cache

import (
	"sync"
	"time"
)

type entry[V any] struct {
	value     V
	expiresAt time.Time
}

// Cache is a generic in-memory TTL cache safe for concurrent use.
type Cache[K comparable, V any] struct {
	mu  sync.RWMutex
	ttl time.Duration
	m   map[K]entry[V]
}

// New creates a Cache whose entries are considered fresh for ttl.
func New[K comparable, V any](ttl time.Duration) *Cache[K, V] {
	return &Cache[K, V]{ttl: ttl, m: make(map[K]entry[V])}
}

// Get returns the cached value and whether it is still fresh. A stale entry
// is still returned (ok=true) so callers can serve-stale-while-revalidate;
// use Fresh to distinguish.
func (c *Cache[K, V]) Get(key K) (V, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	e, found := c.m[key]
	if !found {
		var zero V
		return zero, false
	}
	return e.value, true
}

// Fresh reports whether the cached entry for key exists and has not expired.
func (c *Cache[K, V]) Fresh(key K) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	e, found := c.m[key]
	if !found {
		return false
	}
	return time.Now().Before(e.expiresAt)
}

// Set stores value under key, resetting its expiry.
func (c *Cache[K, V]) Set(key K, value V) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.m[key] = entry[V]{value: value, expiresAt: time.Now().Add(c.ttl)}
}

// Delete evicts key.
func (c *Cache[K, V]) Delete(key K) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.m, key)
}

// Clear evicts all entries.
func (c *Cache[K, V]) Clear() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.m = make(map[K]entry[V])
}

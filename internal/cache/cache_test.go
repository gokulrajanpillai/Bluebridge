package cache

import (
	"testing"
	"time"
)

func TestSetGet(t *testing.T) {
	c := New[string, int](time.Minute)
	c.Set("a", 1)
	v, ok := c.Get("a")
	if !ok || v != 1 {
		t.Fatalf("got (%v, %v), want (1, true)", v, ok)
	}
}

func TestMissing(t *testing.T) {
	c := New[string, int](time.Minute)
	_, ok := c.Get("missing")
	if ok {
		t.Fatal("expected ok=false for missing key")
	}
}

func TestFreshExpiry(t *testing.T) {
	c := New[string, int](10 * time.Millisecond)
	c.Set("a", 1)
	if !c.Fresh("a") {
		t.Fatal("expected fresh immediately after Set")
	}
	time.Sleep(20 * time.Millisecond)
	if c.Fresh("a") {
		t.Fatal("expected stale after ttl elapsed")
	}
	// stale-while-revalidate: value still retrievable after expiry
	v, ok := c.Get("a")
	if !ok || v != 1 {
		t.Fatalf("expected stale value still retrievable, got (%v, %v)", v, ok)
	}
}

func TestDeleteAndClear(t *testing.T) {
	c := New[string, int](time.Minute)
	c.Set("a", 1)
	c.Set("b", 2)
	c.Delete("a")
	if _, ok := c.Get("a"); ok {
		t.Fatal("expected a to be deleted")
	}
	c.Clear()
	if _, ok := c.Get("b"); ok {
		t.Fatal("expected b to be cleared")
	}
}

package logging

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRotatesWhenOverLimit(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bluebridge.log")

	w, err := NewRotatingWriter(path, 10, 3)
	if err != nil {
		t.Fatalf("NewRotatingWriter: %v", err)
	}
	defer w.Close()

	// First write fits under the 10-byte limit.
	if _, err := w.Write([]byte("0123456789")); err != nil {
		t.Fatalf("write 1: %v", err)
	}
	// Second write pushes size over the limit -> rotate before writing.
	if _, err := w.Write([]byte("abc")); err != nil {
		t.Fatalf("write 2: %v", err)
	}

	if _, err := os.Stat(path + ".1"); err != nil {
		t.Fatalf("expected backup %s.1 to exist: %v", path, err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read current log: %v", err)
	}
	if string(data) != "abc" {
		t.Fatalf("current log = %q, want %q", data, "abc")
	}
	backup, err := os.ReadFile(path + ".1")
	if err != nil {
		t.Fatalf("read backup: %v", err)
	}
	if string(backup) != "0123456789" {
		t.Fatalf("backup = %q, want %q", backup, "0123456789")
	}
}

func TestKeepsOnlyMaxBackups(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bluebridge.log")

	w, err := NewRotatingWriter(path, 5, 2)
	if err != nil {
		t.Fatalf("NewRotatingWriter: %v", err)
	}
	defer w.Close()

	// Each write is 5 bytes so every subsequent write triggers a rotation.
	for i := 0; i < 5; i++ {
		if _, err := w.Write([]byte("aaaaa")); err != nil {
			t.Fatalf("write %d: %v", i, err)
		}
	}

	if _, err := os.Stat(path + ".3"); !os.IsNotExist(err) {
		t.Fatalf("expected no .3 backup with maxBackups=2, stat err=%v", err)
	}
	if _, err := os.Stat(path + ".2"); err != nil {
		t.Fatalf("expected .2 backup to exist: %v", err)
	}
	if _, err := os.Stat(path + ".1"); err != nil {
		t.Fatalf("expected .1 backup to exist: %v", err)
	}
}

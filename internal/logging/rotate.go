// Package logging provides a small size-based rotating file writer used as
// the sink for log/slog, per REBUILD_PLAN.md §8 ("10 MB × 3" rotation).
package logging

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// RotatingWriter is an io.Writer that rotates the underlying file once it
// exceeds maxBytes, keeping up to maxBackups previous files (path.1 is the
// newest backup, path.maxBackups the oldest; anything older is deleted).
type RotatingWriter struct {
	mu         sync.Mutex
	path       string
	maxBytes   int64
	maxBackups int
	file       *os.File
	size       int64
}

// NewRotatingWriter opens (creating if needed) path for appending.
func NewRotatingWriter(path string, maxBytes int64, maxBackups int) (*RotatingWriter, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return nil, err
	}
	info, err := f.Stat()
	if err != nil {
		_ = f.Close()
		return nil, err
	}
	return &RotatingWriter{
		path:       path,
		maxBytes:   maxBytes,
		maxBackups: maxBackups,
		file:       f,
		size:       info.Size(),
	}, nil
}

func (w *RotatingWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.size+int64(len(p)) > w.maxBytes && w.size > 0 {
		if err := w.rotate(); err != nil {
			return 0, err
		}
	}
	n, err := w.file.Write(p)
	w.size += int64(n)
	return n, err
}

func (w *RotatingWriter) rotate() error {
	if err := w.file.Close(); err != nil {
		return err
	}
	for i := w.maxBackups; i >= 1; i-- {
		src := w.backupPath(i)
		if i == w.maxBackups {
			_ = os.Remove(src)
			continue
		}
		dst := w.backupPath(i + 1)
		if _, err := os.Stat(src); err == nil {
			_ = os.Rename(src, dst)
		}
	}
	if err := os.Rename(w.path, w.backupPath(1)); err != nil {
		return err
	}
	f, err := os.OpenFile(w.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	w.file = f
	w.size = 0
	return nil
}

func (w *RotatingWriter) backupPath(n int) string {
	return fmt.Sprintf("%s.%d", w.path, n)
}

// Close closes the underlying file.
func (w *RotatingWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.file.Close()
}

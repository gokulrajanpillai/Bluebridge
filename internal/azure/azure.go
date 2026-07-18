// Package azure is the shared Azure service core used by both the localhost
// web server and the interactive CLI. It wraps the ARM REST surface
// (tenants, subscriptions, resources) and the PIM role APIs behind a small
// typed client. It depends only on a TokenFunc for auth, so it is agnostic
// to how tokens are obtained and is trivially testable against httptest.
// See REBUILD_PLAN.md §5.
package azure

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// ARMScope is the OAuth2 scope for Azure Resource Manager.
const ARMScope = "https://management.azure.com/.default"

// DefaultEndpoint is the public ARM endpoint. Tests and the hidden
// --arm-endpoint flag override it to point at a mock server.
const DefaultEndpoint = "https://management.azure.com"

// TokenFunc returns a bearer token for the given tenant and scopes. An empty
// tenantID means "the identity's default/home tenant" (valid for calls like
// GET /tenants that work with any ARM token).
type TokenFunc func(ctx context.Context, tenantID string, scopes []string) (string, error)

// Client talks to ARM. Construct it with NewClient.
type Client struct {
	endpoint string
	token    TokenFunc
	http     *http.Client
	maxRetry int
}

// Option customises a Client.
type Option func(*Client)

// WithEndpoint overrides the ARM base URL (used by tests and --arm-endpoint).
func WithEndpoint(endpoint string) Option {
	return func(c *Client) {
		if endpoint != "" {
			c.endpoint = strings.TrimRight(endpoint, "/")
		}
	}
}

// WithHTTPClient injects a custom *http.Client.
func WithHTTPClient(h *http.Client) Option {
	return func(c *Client) {
		if h != nil {
			c.http = h
		}
	}
}

// NewClient builds a Client. token must be non-nil.
func NewClient(token TokenFunc, opts ...Option) *Client {
	c := &Client{
		endpoint: DefaultEndpoint,
		token:    token,
		http:     &http.Client{Timeout: 60 * time.Second},
		maxRetry: 3,
	}
	for _, o := range opts {
		o(c)
	}
	return c
}

// APIError is the typed error surfaced from every ARM call, mirroring the
// wire error shape and adding an actionable role hint for 403s (A5).
type APIError struct {
	Status    int    `json:"-"`
	Code      string `json:"code"`
	Message   string `json:"message"`
	AzureCode string `json:"azureCode,omitempty"`
	RoleHint  string `json:"roleHint,omitempty"`
}

func (e *APIError) Error() string {
	if e.RoleHint != "" {
		return fmt.Sprintf("%s: %s (%s). %s", e.Code, e.Message, e.AzureCode, e.RoleHint)
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

// IsForbidden reports whether the error is an ARM 403 (authorization failure).
func (e *APIError) IsForbidden() bool { return e.Status == http.StatusForbidden }

// get issues a GET and decodes the JSON body into out. Retries on 429/5xx.
func (c *Client) get(ctx context.Context, tenantID, path, apiVersion string, query url.Values, out any) error {
	return c.do(ctx, http.MethodGet, tenantID, path, apiVersion, query, nil, out)
}

// do performs a request with retry/backoff and typed error handling.
func (c *Client) do(ctx context.Context, method, tenantID, path, apiVersion string, query url.Values, body []byte, out any) error {
	full, err := c.buildURL(path, apiVersion, query)
	if err != nil {
		return err
	}

	token, err := c.token(ctx, tenantID, []string{ARMScope})
	if err != nil {
		return &APIError{Code: "AuthError", Message: "could not acquire access token: " + err.Error()}
	}

	var lastErr error
	for attempt := 0; attempt <= c.maxRetry; attempt++ {
		if attempt > 0 {
			if !sleep(ctx, backoff(attempt)) {
				return ctx.Err()
			}
		}

		var reqBody io.Reader
		if body != nil {
			reqBody = strings.NewReader(string(body))
		}
		req, err := http.NewRequestWithContext(ctx, method, full, reqBody)
		if err != nil {
			return err
		}
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Accept", "application/json")
		if body != nil {
			req.Header.Set("Content-Type", "application/json")
		}

		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = err
			continue // transient transport error: retry
		}

		data, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		switch {
		case resp.StatusCode >= 200 && resp.StatusCode < 300:
			if out == nil || len(data) == 0 {
				return nil
			}
			if err := json.Unmarshal(data, out); err != nil {
				return fmt.Errorf("decode %s: %w", path, err)
			}
			return nil
		case resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode >= 500:
			lastErr = parseAPIError(resp.StatusCode, data)
			if wait := retryAfter(resp); wait > 0 && attempt < c.maxRetry {
				if !sleep(ctx, wait) {
					return ctx.Err()
				}
			}
			continue
		default:
			return parseAPIError(resp.StatusCode, data)
		}
	}
	if apiErr, ok := lastErr.(*APIError); ok {
		return apiErr
	}
	return &APIError{Code: "RequestFailed", Message: fmt.Sprintf("request to %s failed after %d attempts: %v", path, c.maxRetry+1, lastErr)}
}

func (c *Client) buildURL(path, apiVersion string, query url.Values) (string, error) {
	u, err := url.Parse(c.endpoint + path)
	if err != nil {
		return "", err
	}
	q := u.Query()
	for k, vs := range query {
		for _, v := range vs {
			q.Add(k, v)
		}
	}
	if apiVersion != "" {
		q.Set("api-version", apiVersion)
	}
	u.RawQuery = q.Encode()
	return u.String(), nil
}

// getPaged follows ARM `nextLink` pagination, accumulating every page's
// `value` array. Each page is decoded into a value envelope.
func getPaged[T any](ctx context.Context, c *Client, tenantID, path, apiVersion string, query url.Values) ([]T, error) {
	var all []T
	var page listEnvelope[T]
	if err := c.get(ctx, tenantID, path, apiVersion, query, &page); err != nil {
		return nil, err
	}
	all = append(all, page.Value...)

	for page.NextLink != "" {
		next := page.NextLink
		page = listEnvelope[T]{}
		// nextLink is an absolute URL already carrying api-version + skip token.
		if err := c.getAbsolute(ctx, tenantID, next, &page); err != nil {
			return nil, err
		}
		all = append(all, page.Value...)
	}
	return all, nil
}

// getAbsolute GETs a fully-formed URL (an ARM nextLink) rather than building
// one from endpoint+path. It still rewrites the host to the configured
// endpoint so pagination works against a mock server.
func (c *Client) getAbsolute(ctx context.Context, tenantID, rawURL string, out any) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return err
	}
	base, err := url.Parse(c.endpoint)
	if err == nil && base.Host != "" {
		u.Scheme = base.Scheme
		u.Host = base.Host
	}
	return c.get(ctx, tenantID, u.Path, "", u.Query(), out)
}

type listEnvelope[T any] struct {
	Value    []T    `json:"value"`
	NextLink string `json:"nextLink"`
}

func parseAPIError(status int, data []byte) *APIError {
	e := &APIError{Status: status, Code: http.StatusText(status), Message: strings.TrimSpace(string(data))}
	var wire struct {
		Error struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if json.Unmarshal(data, &wire) == nil && wire.Error.Code != "" {
		e.AzureCode = wire.Error.Code
		e.Message = wire.Error.Message
		e.Code = http.StatusText(status)
	}
	if status == http.StatusForbidden {
		e.RoleHint = "You lack a required RBAC role on this scope. A Reader role is the usual minimum."
	}
	return e
}

func retryAfter(resp *http.Response) time.Duration {
	if v := resp.Header.Get("Retry-After"); v != "" {
		if secs, err := strconv.Atoi(v); err == nil {
			return time.Duration(secs) * time.Second
		}
	}
	return 0
}

func backoff(attempt int) time.Duration {
	// 200ms, 400ms, 800ms, ...
	return time.Duration(200*(1<<(attempt-1))) * time.Millisecond
}

// sleep waits d or until ctx is cancelled; returns false if cancelled.
func sleep(ctx context.Context, d time.Duration) bool {
	if d <= 0 {
		return true
	}
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}

package azure

import "context"

const tenantsAPIVersion = "2022-12-01"

// Tenants returns every tenant the signed-in identity belongs to. Works with
// any ARM token, so it uses the default-tenant token.
func (c *Client) Tenants(ctx context.Context) ([]Tenant, error) {
	return getPaged[Tenant](ctx, c, "", "/tenants", tenantsAPIVersion, nil)
}

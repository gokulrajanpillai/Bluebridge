package azure

import (
	"context"
	"net/url"
	"strconv"
	"strings"
)

const resourcesAPIVersion = "2021-04-01"

// wire shape for GET /subscriptions/{sid}/resources
type resourceWire struct {
	ID       string            `json:"id"`
	Name     string            `json:"name"`
	Type     string            `json:"type"`
	Location string            `json:"location"`
	Kind     string            `json:"kind"`
	Tags     map[string]string `json:"tags"`
}

// ResourceOptions filters a resource listing.
type ResourceOptions struct {
	// Filter is a raw ARM $filter expression (optional).
	Filter string
	// Top caps the number of results (0 = server default).
	Top int
}

// Resources lists resources in a subscription. Kept deliberately simple
// (per-subscription ARM listing); the web SPA upgrades this to Resource
// Graph for cross-subscription queries in a later milestone (REBUILD_PLAN §5.3).
func (c *Client) Resources(ctx context.Context, tenantID, subscriptionID string, opts ResourceOptions) ([]Resource, error) {
	q := url.Values{}
	if opts.Filter != "" {
		q.Set("$filter", opts.Filter)
	}
	if opts.Top > 0 {
		q.Set("$top", strconv.Itoa(opts.Top))
	}
	raw, err := getPaged[resourceWire](ctx, c, tenantID,
		"/subscriptions/"+subscriptionID+"/resources", resourcesAPIVersion, q)
	if err != nil {
		return nil, err
	}
	out := make([]Resource, 0, len(raw))
	for _, r := range raw {
		out = append(out, Resource{
			ID:            r.ID,
			Name:          r.Name,
			Type:          r.Type,
			Location:      r.Location,
			Kind:          r.Kind,
			Tags:          r.Tags,
			ResourceGroup: resourceGroupFromID(r.ID),
		})
	}
	return out, nil
}

// resourceGroupFromID extracts the resource group segment from an ARM ID.
func resourceGroupFromID(id string) string {
	parts := strings.Split(strings.Trim(id, "/"), "/")
	for i := 0; i+1 < len(parts); i++ {
		if strings.EqualFold(parts[i], "resourceGroups") {
			return parts[i+1]
		}
	}
	return ""
}

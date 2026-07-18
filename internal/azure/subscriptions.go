package azure

import "context"

const subscriptionsAPIVersion = "2022-12-01"

// wire shape for GET /subscriptions
type subscriptionWire struct {
	SubscriptionID string `json:"subscriptionId"`
	DisplayName    string `json:"displayName"`
	State          string `json:"state"`
	TenantID       string `json:"tenantId"`
}

// Subscriptions lists the subscriptions visible in tenantID. The token is
// acquired for that tenant so cross-tenant subscriptions are scoped correctly.
func (c *Client) Subscriptions(ctx context.Context, tenantID string) ([]Subscription, error) {
	raw, err := getPaged[subscriptionWire](ctx, c, tenantID, "/subscriptions", subscriptionsAPIVersion, nil)
	if err != nil {
		return nil, err
	}
	subs := make([]Subscription, 0, len(raw))
	for _, s := range raw {
		tid := s.TenantID
		if tid == "" {
			tid = tenantID
		}
		subs = append(subs, Subscription{
			SubscriptionID: s.SubscriptionID,
			DisplayName:    s.DisplayName,
			State:          s.State,
			TenantID:       tid,
		})
	}
	return subs, nil
}

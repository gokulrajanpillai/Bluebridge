package azure

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"

	"github.com/google/uuid"
)

const pimAPIVersion = "2020-10-01"

// eligibility wire shapes
type eligibilityWire struct {
	Properties struct {
		RoleDefinitionID   string `json:"roleDefinitionId"`
		PrincipalID        string `json:"principalId"`
		Scope              string `json:"scope"`
		EndDateTime        string `json:"endDateTime"`
		ExpandedProperties struct {
			RoleDefinition struct {
				DisplayName string `json:"displayName"`
			} `json:"roleDefinition"`
			Scope struct {
				DisplayName string `json:"displayName"`
			} `json:"scope"`
		} `json:"expandedProperties"`
	} `json:"properties"`
}

// EligibleRoles lists PIM roles the signed-in user can activate at scope
// (e.g. "/subscriptions/{id}"). tenantID scopes the access token.
func (c *Client) EligibleRoles(ctx context.Context, tenantID, scope string) ([]EligibleRole, error) {
	q := url.Values{}
	q.Set("$filter", "asTarget()")
	path := "/" + trimSlash(scope) + "/providers/Microsoft.Authorization/roleEligibilityScheduleInstances"
	raw, err := getPaged[eligibilityWire](ctx, c, tenantID, path, pimAPIVersion, q)
	if err != nil {
		return nil, err
	}
	roles := make([]EligibleRole, 0, len(raw))
	for _, e := range raw {
		p := e.Properties
		roles = append(roles, EligibleRole{
			Name:             p.ExpandedProperties.RoleDefinition.DisplayName,
			RoleDefinitionID: p.RoleDefinitionID,
			Scope:            p.Scope,
			ScopeDisplay:     firstNonEmpty(p.ExpandedProperties.Scope.DisplayName, p.Scope),
			PrincipalID:      p.PrincipalID,
			EndDateTime:      p.EndDateTime,
		})
	}
	return roles, nil
}

type activationRequestBody struct {
	Properties struct {
		PrincipalID      string `json:"principalId"`
		RoleDefinitionID string `json:"roleDefinitionId"`
		RequestType      string `json:"requestType"`
		Justification    string `json:"justification"`
		ScheduleInfo     struct {
			Expiration struct {
				Type     string `json:"type"`
				Duration string `json:"duration"`
			} `json:"expiration"`
		} `json:"scheduleInfo"`
	} `json:"properties"`
}

type activationResponse struct {
	Name       string `json:"name"`
	Properties struct {
		Status string `json:"status"`
	} `json:"properties"`
}

// ActivateRole submits a self-activation request for one eligible role and
// returns the initial (usually non-terminal) status plus the request ID for
// polling. RoleName is echoed back for display.
func (c *Client) ActivateRole(ctx context.Context, tenantID, roleName string, req ActivationRequest) (ActivationResult, error) {
	requestID := uuid.NewString()

	var body activationRequestBody
	body.Properties.PrincipalID = req.PrincipalID
	body.Properties.RoleDefinitionID = req.RoleDefinitionID
	body.Properties.RequestType = "SelfActivate"
	body.Properties.Justification = req.Justification
	body.Properties.ScheduleInfo.Expiration.Type = "AfterDuration"
	body.Properties.ScheduleInfo.Expiration.Duration = fmt.Sprintf("PT%dH", clampDuration(req.DurationHours))

	payload, err := json.Marshal(body)
	if err != nil {
		return ActivationResult{}, err
	}

	path := "/" + trimSlash(req.Scope) +
		"/providers/Microsoft.Authorization/roleAssignmentScheduleRequests/" + requestID

	var resp activationResponse
	if err := c.do(ctx, "PUT", tenantID, path, pimAPIVersion, nil, payload, &resp); err != nil {
		return ActivationResult{}, err
	}
	return ActivationResult{
		RequestID: requestID,
		Scope:     req.Scope,
		RoleName:  roleName,
		Status:    resp.Properties.Status,
	}, nil
}

// ActivationStatus polls the status of a previously submitted activation.
func (c *Client) ActivationStatus(ctx context.Context, tenantID, scope, requestID string) (ActivationResult, error) {
	path := "/" + trimSlash(scope) +
		"/providers/Microsoft.Authorization/roleAssignmentScheduleRequests/" + requestID
	var resp activationResponse
	if err := c.get(ctx, tenantID, path, pimAPIVersion, nil, &resp); err != nil {
		return ActivationResult{}, err
	}
	return ActivationResult{RequestID: requestID, Scope: scope, Status: resp.Properties.Status}, nil
}

func clampDuration(h int) int {
	if h < 1 {
		return 1
	}
	if h > 8 {
		return 8
	}
	return h
}

func trimSlash(s string) string {
	for len(s) > 0 && s[0] == '/' {
		s = s[1:]
	}
	for len(s) > 0 && s[len(s)-1] == '/' {
		s = s[:len(s)-1]
	}
	return s
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

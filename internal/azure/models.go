package azure

// Tenant is an Entra tenant the signed-in identity can access.
type Tenant struct {
	TenantID      string `json:"tenantId"`
	DisplayName   string `json:"displayName"`
	DefaultDomain string `json:"defaultDomain"`
}

// Subscription is an Azure subscription within a tenant.
type Subscription struct {
	SubscriptionID string `json:"subscriptionId"`
	DisplayName    string `json:"displayName"`
	State          string `json:"state"`
	TenantID       string `json:"tenantId"`
}

// Resource is a single Azure resource (ARM generic view).
type Resource struct {
	ID            string            `json:"id"`
	Name          string            `json:"name"`
	Type          string            `json:"type"`
	Location      string            `json:"location"`
	ResourceGroup string            `json:"resourceGroup,omitempty"`
	Kind          string            `json:"kind,omitempty"`
	Tags          map[string]string `json:"tags,omitempty"`
}

// EligibleRole is a PIM role the user can activate at a scope.
type EligibleRole struct {
	// Name is the role definition display name (e.g. "Contributor").
	Name string `json:"name"`
	// RoleDefinitionID is the fully-qualified role definition resource ID.
	RoleDefinitionID string `json:"roleDefinitionId"`
	// Scope is where the eligibility applies (subscription or narrower).
	Scope string `json:"scope"`
	// ScopeDisplay is a friendly label for the scope.
	ScopeDisplay string `json:"scopeDisplay"`
	// PrincipalID is the signed-in user's object ID (needed to activate).
	PrincipalID string `json:"principalId"`
	// EndDateTime is when the eligibility itself expires (may be empty).
	EndDateTime string `json:"endDateTime,omitempty"`
}

// ActivationRequest asks to self-activate one eligible role.
type ActivationRequest struct {
	Scope            string
	RoleDefinitionID string
	PrincipalID      string
	Justification    string
	DurationHours    int
}

// ActivationResult reports the outcome of an activation request.
type ActivationResult struct {
	RequestID string `json:"requestId"`
	Scope     string `json:"scope"`
	RoleName  string `json:"roleName"`
	// Status is the ARM request status: PendingApproval, Provisioning,
	// Provisioned, Denied, Failed, Canceled, ...
	Status string `json:"status"`
}

// IsTerminal reports whether an activation status will not change further.
func (r ActivationResult) IsTerminal() bool {
	switch r.Status {
	case "Provisioned", "Denied", "Failed", "Canceled", "Revoked":
		return true
	default:
		return false
	}
}

// Succeeded reports whether the activation completed successfully.
func (r ActivationResult) Succeeded() bool { return r.Status == "Provisioned" }

package azure

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestSubscriptionsMapsTenantFallback(t *testing.T) {
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/subscriptions") {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		w.Write([]byte(`{"value":[
			{"subscriptionId":"sub-1","displayName":"Prod","state":"Enabled"},
			{"subscriptionId":"sub-2","displayName":"Dev","state":"Enabled","tenantId":"other"}
		]}`))
	}))
	subs, err := c.Subscriptions(context.Background(), "tenant-A")
	if err != nil {
		t.Fatalf("Subscriptions: %v", err)
	}
	if len(subs) != 2 {
		t.Fatalf("got %d subs", len(subs))
	}
	if subs[0].TenantID != "tenant-A" {
		t.Errorf("sub-1 tenant fallback = %q, want tenant-A", subs[0].TenantID)
	}
	if subs[1].TenantID != "other" {
		t.Errorf("sub-2 tenant = %q, want other", subs[1].TenantID)
	}
}

func TestResourcesExtractsResourceGroup(t *testing.T) {
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"value":[
			{"id":"/subscriptions/s1/resourceGroups/rg-payments/providers/Microsoft.Storage/storageAccounts/acct","name":"acct","type":"Microsoft.Storage/storageAccounts","location":"eastus"}
		]}`))
	}))
	res, err := c.Resources(context.Background(), "t", "s1", ResourceOptions{})
	if err != nil {
		t.Fatalf("Resources: %v", err)
	}
	if len(res) != 1 || res[0].ResourceGroup != "rg-payments" {
		t.Fatalf("resource group extraction failed: %+v", res)
	}
}

func TestEligibleRolesParsesExpandedNames(t *testing.T) {
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("$filter"); got != "asTarget()" {
			t.Errorf("$filter = %q, want asTarget()", got)
		}
		w.Write([]byte(`{"value":[
			{"properties":{
				"roleDefinitionId":"/subscriptions/s1/providers/Microsoft.Authorization/roleDefinitions/rd-1",
				"principalId":"user-1",
				"scope":"/subscriptions/s1",
				"expandedProperties":{"roleDefinition":{"displayName":"Contributor"},"scope":{"displayName":"Prod Sub"}}
			}}
		]}`))
	}))
	roles, err := c.EligibleRoles(context.Background(), "t", "/subscriptions/s1")
	if err != nil {
		t.Fatalf("EligibleRoles: %v", err)
	}
	if len(roles) != 1 {
		t.Fatalf("got %d roles", len(roles))
	}
	r := roles[0]
	if r.Name != "Contributor" || r.ScopeDisplay != "Prod Sub" || r.PrincipalID != "user-1" {
		t.Fatalf("role parse = %+v", r)
	}
}

func TestActivateRoleSendsSelfActivateBody(t *testing.T) {
	var body activationRequestBody
	var method, path string
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		method, path = r.Method, r.URL.Path
		data, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(data, &body)
		w.Write([]byte(`{"name":"req-guid","properties":{"status":"PendingApproval"}}`))
	}))
	res, err := c.ActivateRole(context.Background(), "t", "Contributor", ActivationRequest{
		Scope:            "/subscriptions/s1",
		RoleDefinitionID: "rd-1",
		PrincipalID:      "user-1",
		Justification:    "on-call",
		DurationHours:    4,
	})
	if err != nil {
		t.Fatalf("ActivateRole: %v", err)
	}
	if method != http.MethodPut {
		t.Errorf("method = %s, want PUT", method)
	}
	if !strings.Contains(path, "roleAssignmentScheduleRequests/") {
		t.Errorf("path = %s", path)
	}
	if body.Properties.RequestType != "SelfActivate" {
		t.Errorf("requestType = %q", body.Properties.RequestType)
	}
	if body.Properties.ScheduleInfo.Expiration.Duration != "PT4H" {
		t.Errorf("duration = %q, want PT4H", body.Properties.ScheduleInfo.Expiration.Duration)
	}
	if res.Status != "PendingApproval" || res.RoleName != "Contributor" {
		t.Errorf("result = %+v", res)
	}
	if res.IsTerminal() {
		t.Errorf("PendingApproval should not be terminal")
	}
}

func TestActivateRoleClampsDuration(t *testing.T) {
	var body activationRequestBody
	c := testClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		data, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(data, &body)
		w.Write([]byte(`{"name":"g","properties":{"status":"Provisioned"}}`))
	}))
	res, err := c.ActivateRole(context.Background(), "t", "Reader", ActivationRequest{
		Scope: "/subscriptions/s1", DurationHours: 99,
	})
	if err != nil {
		t.Fatalf("ActivateRole: %v", err)
	}
	if body.Properties.ScheduleInfo.Expiration.Duration != "PT8H" {
		t.Errorf("duration clamp = %q, want PT8H", body.Properties.ScheduleInfo.Expiration.Duration)
	}
	if !res.Succeeded() || !res.IsTerminal() {
		t.Errorf("Provisioned should be terminal+succeeded: %+v", res)
	}
}

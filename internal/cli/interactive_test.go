package cli

import (
	"bytes"
	"context"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/exp/teatest"

	"github.com/gokulrajanpillai/bluebridge/internal/azure"
)

// fakeClient is an in-memory rolesProvider for the E2E test — no live ARM.
type fakeClient struct {
	activated []azure.ActivationRequest
}

func (f *fakeClient) Tenants(context.Context) ([]azure.Tenant, error) {
	return []azure.Tenant{{TenantID: "tenant-1", DisplayName: "Contoso"}}, nil
}

func (f *fakeClient) Subscriptions(context.Context, string) ([]azure.Subscription, error) {
	return []azure.Subscription{{SubscriptionID: "sub-1", DisplayName: "Prod", State: "Enabled"}}, nil
}

func (f *fakeClient) EligibleRoles(context.Context, string, string) ([]azure.EligibleRole, error) {
	return []azure.EligibleRole{
		{Name: "Contributor", RoleDefinitionID: "rd-1", Scope: "/subscriptions/sub-1", ScopeDisplay: "Prod", PrincipalID: "user-1"},
		{Name: "Reader", RoleDefinitionID: "rd-2", Scope: "/subscriptions/sub-1", ScopeDisplay: "Prod", PrincipalID: "user-1"},
	}, nil
}

func (f *fakeClient) ActivateRole(_ context.Context, _, roleName string, req azure.ActivationRequest) (azure.ActivationResult, error) {
	f.activated = append(f.activated, req)
	return azure.ActivationResult{RequestID: "r-" + roleName, Scope: req.Scope, RoleName: roleName, Status: "Provisioned"}, nil
}

func waitFor(t *testing.T, tm *teatest.TestModel, substr string) {
	t.Helper()
	teatest.WaitFor(t, tm.Output(), func(b []byte) bool {
		return bytes.Contains(b, []byte(substr))
	}, teatest.WithDuration(3*time.Second))
}

// TestInteractiveHappyPath drives the whole flow headlessly:
// tenants -> subscription -> multi-select a role -> justify -> activate.
func TestInteractiveHappyPath(t *testing.T) {
	fc := &fakeClient{}
	tm := teatest.NewTestModel(t, NewModel(context.Background(), fc, "user@contoso.com"),
		teatest.WithInitialTermSize(100, 40))

	waitFor(t, tm, "Select a tenant")
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter}) // pick Contoso

	waitFor(t, tm, "Select a subscription")
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter}) // pick Prod

	waitFor(t, tm, "Eligible roles")
	tm.Send(tea.KeyMsg{Type: tea.KeySpace}) // check Contributor
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter}) // continue

	waitFor(t, tm, "Justification")
	tm.Send(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("on-call incident")}) // justification
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter})                                    // activate

	waitFor(t, tm, "Activation results")
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter}) // exit

	tm.WaitFinished(t, teatest.WithFinalTimeout(3*time.Second))

	if len(fc.activated) != 1 {
		t.Fatalf("expected 1 activation, got %d", len(fc.activated))
	}
	got := fc.activated[0]
	if got.Justification != "on-call incident" {
		t.Errorf("justification = %q", got.Justification)
	}
	if got.DurationHours != 4 {
		t.Errorf("duration = %d, want default 4", got.DurationHours)
	}
	if got.RoleDefinitionID != "rd-1" {
		t.Errorf("activated wrong role: %+v", got)
	}
}

// TestJustificationRequired verifies that pressing enter with an empty
// justification does not submit.
func TestJustificationRequired(t *testing.T) {
	fc := &fakeClient{}
	tm := teatest.NewTestModel(t, NewModel(context.Background(), fc, "user@contoso.com"),
		teatest.WithInitialTermSize(100, 40))

	waitFor(t, tm, "Select a tenant")
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter})
	waitFor(t, tm, "Select a subscription")
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter})
	waitFor(t, tm, "Eligible roles")
	tm.Send(tea.KeyMsg{Type: tea.KeySpace})
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter})
	waitFor(t, tm, "Justification")
	tm.Send(tea.KeyMsg{Type: tea.KeyEnter}) // empty -> should NOT activate

	tm.Send(tea.KeyMsg{Type: tea.KeyCtrlC}) // quit
	tm.WaitFinished(t, teatest.WithFinalTimeout(3*time.Second))

	if len(fc.activated) != 0 {
		t.Fatalf("empty justification must not activate, got %d activations", len(fc.activated))
	}
}

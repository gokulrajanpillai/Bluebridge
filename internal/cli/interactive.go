// Package cli implements the interactive BlueBridge terminal UI and its
// non-interactive subcommands. The interactive flow is:
// login -> pick tenant -> pick subscription (scope) -> multi-select eligible
// PIM roles -> justify + duration -> activate and watch status.
package cli

import (
	"context"
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/gokulrajanpillai/bluebridge/internal/azure"
)

type step int

const (
	stepLoadingTenants step = iota
	stepTenants
	stepLoadingScopes
	stepScopes
	stepLoadingRoles
	stepRoles
	stepJustify
	stepActivating
	stepDone
	stepError
)

// rolesProvider is the subset of *azure.Client the model needs. Defining it
// as an interface lets tests inject a fake without a live ARM endpoint.
type rolesProvider interface {
	Tenants(ctx context.Context) ([]azure.Tenant, error)
	Subscriptions(ctx context.Context, tenantID string) ([]azure.Subscription, error)
	EligibleRoles(ctx context.Context, tenantID, scope string) ([]azure.EligibleRole, error)
	ActivateRole(ctx context.Context, tenantID, roleName string, req azure.ActivationRequest) (azure.ActivationResult, error)
}

// message types for async ARM calls
type tenantsMsg struct{ tenants []azure.Tenant }
type scopesMsg struct{ subs []azure.Subscription }
type rolesMsg struct{ roles []azure.EligibleRole }
type activatedMsg struct{ results []azure.ActivationResult }
type errMsg struct{ err error }

var (
	titleStyle    = lipgloss.NewStyle().Bold(true)
	cursorStyle   = lipgloss.NewStyle().Bold(true)
	selectedStyle = lipgloss.NewStyle().Bold(true)
	faintStyle    = lipgloss.NewStyle().Faint(true)
	okStyle       = lipgloss.NewStyle().Bold(true)
	errStyle      = lipgloss.NewStyle().Bold(true)
)

type model struct {
	client   rolesProvider
	ctx      context.Context
	username string

	step    step
	spinner spinner.Model
	justify textinput.Model
	err     error

	tenants  []azure.Tenant
	tenant   azure.Tenant
	subs     []azure.Subscription
	sub      azure.Subscription
	roles    []azure.EligibleRole
	checked  []bool
	cursor   int
	duration int

	results []azure.ActivationResult
}

// NewModel builds the interactive model. username is shown in the header.
func NewModel(ctx context.Context, client rolesProvider, username string) model {
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	ti := textinput.New()
	ti.Placeholder = "reason for activation (required)"
	ti.CharLimit = 200
	return model{
		client:   client,
		ctx:      ctx,
		username: username,
		step:     stepLoadingTenants,
		spinner:  sp,
		justify:  ti,
		duration: 4,
	}
}

func (m model) Init() tea.Cmd {
	return tea.Batch(m.spinner.Tick, m.loadTenants())
}

func (m model) loadTenants() tea.Cmd {
	return func() tea.Msg {
		ts, err := m.client.Tenants(m.ctx)
		if err != nil {
			return errMsg{err}
		}
		return tenantsMsg{ts}
	}
}

func (m model) loadScopes(tenantID string) tea.Cmd {
	return func() tea.Msg {
		subs, err := m.client.Subscriptions(m.ctx, tenantID)
		if err != nil {
			return errMsg{err}
		}
		return scopesMsg{subs}
	}
}

func (m model) loadRoles(tenantID, scope string) tea.Cmd {
	return func() tea.Msg {
		roles, err := m.client.EligibleRoles(m.ctx, tenantID, scope)
		if err != nil {
			return errMsg{err}
		}
		return rolesMsg{roles}
	}
}

func (m model) activate() tea.Cmd {
	return func() tea.Msg {
		var results []azure.ActivationResult
		for i, r := range m.roles {
			if !m.checked[i] {
				continue
			}
			res, err := m.client.ActivateRole(m.ctx, m.tenant.TenantID, r.Name, azure.ActivationRequest{
				Scope:            r.Scope,
				RoleDefinitionID: r.RoleDefinitionID,
				PrincipalID:      r.PrincipalID,
				Justification:    m.justify.Value(),
				DurationHours:    m.duration,
			})
			if err != nil {
				res = azure.ActivationResult{Scope: r.Scope, RoleName: r.Name, Status: "Failed: " + err.Error()}
			}
			results = append(results, res)
		}
		return activatedMsg{results}
	}
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		return m.handleKey(msg)
	case tenantsMsg:
		m.tenants = msg.tenants
		m.step = stepTenants
		m.cursor = 0
		return m, nil
	case scopesMsg:
		m.subs = msg.subs
		m.step = stepScopes
		m.cursor = 0
		return m, nil
	case rolesMsg:
		m.roles = msg.roles
		m.checked = make([]bool, len(msg.roles))
		m.step = stepRoles
		m.cursor = 0
		return m, nil
	case activatedMsg:
		m.results = msg.results
		m.step = stepDone
		return m, nil
	case errMsg:
		m.err = msg.err
		m.step = stepError
		return m, nil
	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	if m.step == stepJustify {
		var cmd tea.Cmd
		m.justify, cmd = m.justify.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "ctrl+c", "esc":
		return m, tea.Quit
	case "q":
		if m.step != stepJustify { // let q be typed in the justification box
			return m, tea.Quit
		}
	}

	switch m.step {
	case stepTenants:
		return m.keyList(msg, len(m.tenants), func() (tea.Model, tea.Cmd) {
			m.tenant = m.tenants[m.cursor]
			m.step = stepLoadingScopes
			return m, tea.Batch(m.spinner.Tick, m.loadScopes(m.tenant.TenantID))
		})
	case stepScopes:
		return m.keyList(msg, len(m.subs), func() (tea.Model, tea.Cmd) {
			m.sub = m.subs[m.cursor]
			m.step = stepLoadingRoles
			scope := "/subscriptions/" + m.sub.SubscriptionID
			return m, tea.Batch(m.spinner.Tick, m.loadRoles(m.tenant.TenantID, scope))
		})
	case stepRoles:
		return m.keyRoles(msg)
	case stepJustify:
		return m.keyJustify(msg)
	case stepDone, stepError:
		if msg.String() == "enter" {
			return m, tea.Quit
		}
	}
	return m, nil
}

// keyList handles up/down/enter for a single-select list.
func (m model) keyList(msg tea.KeyMsg, n int, onEnter func() (tea.Model, tea.Cmd)) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "up", "k":
		if m.cursor > 0 {
			m.cursor--
		}
	case "down", "j":
		if m.cursor < n-1 {
			m.cursor++
		}
	case "enter":
		if n > 0 {
			return onEnter()
		}
	}
	return m, nil
}

func (m model) keyRoles(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "up", "k":
		if m.cursor > 0 {
			m.cursor--
		}
	case "down", "j":
		if m.cursor < len(m.roles)-1 {
			m.cursor++
		}
	case " ":
		if len(m.checked) > 0 {
			m.checked[m.cursor] = !m.checked[m.cursor]
		}
	case "a":
		all := !m.allChecked()
		for i := range m.checked {
			m.checked[i] = all
		}
	case "enter":
		if m.countChecked() > 0 {
			m.step = stepJustify
			m.justify.Focus()
			return m, textinput.Blink
		}
	}
	return m, nil
}

func (m model) keyJustify(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "up":
		if m.duration < 8 {
			m.duration++
		}
		return m, nil
	case "down":
		if m.duration > 1 {
			m.duration--
		}
		return m, nil
	case "enter":
		if strings.TrimSpace(m.justify.Value()) == "" {
			return m, nil // justification required
		}
		m.step = stepActivating
		return m, tea.Batch(m.spinner.Tick, m.activate())
	}
	var cmd tea.Cmd
	m.justify, cmd = m.justify.Update(msg)
	return m, cmd
}

func (m model) allChecked() bool {
	for _, c := range m.checked {
		if !c {
			return false
		}
	}
	return len(m.checked) > 0
}

func (m model) countChecked() int {
	n := 0
	for _, c := range m.checked {
		if c {
			n++
		}
	}
	return n
}

func (m model) View() string {
	var b strings.Builder
	fmt.Fprintf(&b, "%s  %s\n\n", titleStyle.Render("🌉 BlueBridge"), faintStyle.Render(m.username))

	switch m.step {
	case stepLoadingTenants:
		fmt.Fprintf(&b, "%s Loading tenants...\n", m.spinner.View())
	case stepTenants:
		b.WriteString(titleStyle.Render("Select a tenant") + "\n\n")
		for i, t := range m.tenants {
			label := t.DisplayName
			if label == "" {
				label = t.TenantID
			}
			b.WriteString(renderRow(i == m.cursor, false, fmt.Sprintf("%s  %s", label, faintStyle.Render(t.TenantID))))
		}
		b.WriteString(footer("↑/↓ move · enter select · q quit"))
	case stepLoadingScopes:
		fmt.Fprintf(&b, "%s Loading subscriptions in %s...\n", m.spinner.View(), m.tenant.DisplayName)
	case stepScopes:
		fmt.Fprintf(&b, "%s\n\n", titleStyle.Render("Select a subscription (scope)"))
		for i, s := range m.subs {
			b.WriteString(renderRow(i == m.cursor, false, fmt.Sprintf("%s  %s", s.DisplayName, faintStyle.Render(s.SubscriptionID))))
		}
		b.WriteString(footer("↑/↓ move · enter select · q quit"))
	case stepLoadingRoles:
		fmt.Fprintf(&b, "%s Loading eligible roles...\n", m.spinner.View())
	case stepRoles:
		fmt.Fprintf(&b, "%s\n\n", titleStyle.Render("Eligible roles — select to activate"))
		if len(m.roles) == 0 {
			b.WriteString(faintStyle.Render("No eligible PIM roles at this scope.\n"))
		}
		for i, r := range m.roles {
			b.WriteString(renderRow(i == m.cursor, m.checked[i], fmt.Sprintf("%s  %s", r.Name, faintStyle.Render(r.ScopeDisplay))))
		}
		fmt.Fprintf(&b, "\n%s selected", selectedStyle.Render(fmt.Sprintf("%d", m.countChecked())))
		b.WriteString(footer("space toggle · a all · enter continue · q quit"))
	case stepJustify:
		fmt.Fprintf(&b, "%s\n\n", titleStyle.Render(fmt.Sprintf("Activate %d role(s)", m.countChecked())))
		fmt.Fprintf(&b, "Justification:\n%s\n\n", m.justify.View())
		fmt.Fprintf(&b, "Duration: %s hours  %s\n", selectedStyle.Render(fmt.Sprintf("%d", m.duration)), faintStyle.Render("(↑/↓ to change)"))
		b.WriteString(footer("enter activate · esc cancel"))
	case stepActivating:
		fmt.Fprintf(&b, "%s Submitting activation requests...\n", m.spinner.View())
	case stepDone:
		b.WriteString(okStyle.Render("Activation results") + "\n\n")
		for _, r := range m.results {
			icon := statusIcon(r)
			fmt.Fprintf(&b, "  %s  %s  %s\n", icon, r.RoleName, faintStyle.Render(r.Status))
		}
		b.WriteString(footer("enter to exit"))
	case stepError:
		fmt.Fprintf(&b, "%s %s\n", errStyle.Render("Error:"), m.err)
		b.WriteString(footer("enter to exit"))
	}
	return b.String()
}

func renderRow(cursor, checked bool, text string) string {
	prefix := "  "
	if cursor {
		prefix = cursorStyle.Render("▸ ")
	}
	box := ""
	if checked {
		box = selectedStyle.Render("[x] ")
	} else {
		box = "[ ] "
	}
	// The checkbox is only meaningful for multi-select lists; single-select
	// lists pass checked=false and we still render a clean row.
	return fmt.Sprintf("%s%s%s\n", prefix, box, text)
}

func footer(help string) string {
	return "\n\n" + faintStyle.Render(help) + "\n"
}

func statusIcon(r azure.ActivationResult) string {
	switch {
	case r.Succeeded():
		return okStyle.Render("✓")
	case strings.HasPrefix(r.Status, "Failed"), r.Status == "Denied":
		return errStyle.Render("✗")
	default:
		return "⏳"
	}
}

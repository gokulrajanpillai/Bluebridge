package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/gokulrajanpillai/bluebridge/internal/auth"
	"github.com/gokulrajanpillai/bluebridge/internal/azure"
)

// Run is the CLI entrypoint. It parses flags, signs in, and either runs a
// non-interactive subcommand or launches the interactive TUI. It returns a
// process exit code.
func Run(args []string, version string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("bluebridge", flag.ContinueOnError)
	fs.SetOutput(stderr)
	tenant := fs.String("tenant", "", "tenant ID to sign in to")
	deviceCode := fs.Bool("device-code", false, "use device-code sign-in (headless/SSH)")
	azCLI := fs.Bool("az-cli", false, "reuse an existing Azure CLI login")
	armEndpoint := fs.String("arm-endpoint", "", "override ARM endpoint (testing)")
	showVersion := fs.Bool("version", false, "print version and exit")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *showVersion {
		fmt.Fprintln(stdout, version)
		return 0
	}

	method := auth.MethodBrowser
	switch {
	case *deviceCode:
		method = auth.MethodDeviceCode
	case *azCLI:
		method = auth.MethodAzureCLI
	}

	ctx := context.Background()

	account, tokens, err := signIn(ctx, method, *tenant, stderr)
	if err != nil {
		fmt.Fprintf(stderr, "sign-in failed: %v\n", err)
		return 1
	}
	client := azure.NewClient(tokens.Token, azure.WithEndpoint(*armEndpoint))

	rest := fs.Args()
	if len(rest) == 0 {
		return runInteractive(ctx, client, account.Username, stdout)
	}
	return runCommand(ctx, client, account, rest, stdout, stderr)
}

// signIn performs the initial interactive sign-in (to surface auth errors and
// derive the account) and returns a per-tenant token provider sharing the
// same encrypted cache.
func signIn(ctx context.Context, method auth.Method, tenant string, stderr io.Writer) (auth.Account, *auth.TenantTokens, error) {
	var cache azidentity.Cache
	if c, err := auth.NewPersistentCache(); err == nil {
		cache = c
	} else {
		fmt.Fprintf(stderr, "warning: persistent token cache unavailable (%v); sign-in will not survive restart\n", err)
	}

	broker := auth.New(cache)
	broker.OnDeviceCode(func(p auth.DeviceCodePrompt) {
		fmt.Fprintf(stderr, "\nTo sign in, open %s and enter code %s\n\n", p.VerificationURL, p.UserCode)
	})
	account, err := broker.SignIn(ctx, tenant, method)
	if err != nil {
		return auth.Account{}, nil, err
	}
	return account, auth.NewTenantTokens(method, cache), nil
}

func runInteractive(ctx context.Context, client rolesProvider, username string, stdout io.Writer) int {
	p := tea.NewProgram(NewModel(ctx, client, username), tea.WithOutput(stdout))
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(stdout, "error:", err)
		return 1
	}
	return 0
}

// runCommand dispatches the non-interactive subcommands used for scripting.
func runCommand(ctx context.Context, client *azure.Client, account auth.Account, args []string, stdout, stderr io.Writer) int {
	switch args[0] {
	case "tenants":
		ts, err := client.Tenants(ctx)
		if err != nil {
			return fail(stderr, err)
		}
		for _, t := range ts {
			fmt.Fprintf(stdout, "%s\t%s\n", t.TenantID, t.DisplayName)
		}
		return 0

	case "resources":
		sub := valueFlag(args[1:], "--sub")
		tenant := valueFlag(args[1:], "--tenant")
		if sub == "" {
			return fail(stderr, errors.New("resources requires --sub <subscriptionId>"))
		}
		res, err := client.Resources(ctx, tenant, sub, azure.ResourceOptions{})
		if err != nil {
			return fail(stderr, err)
		}
		for _, r := range res {
			fmt.Fprintf(stdout, "%s\t%s\t%s\n", r.Name, r.Type, r.Location)
		}
		return 0

	case "pim":
		return runPIM(ctx, client, args[1:], stdout, stderr)

	default:
		fmt.Fprintf(stderr, "unknown command %q; try: tenants, resources, pim\n", args[0])
		return 2
	}
}

func runPIM(ctx context.Context, client *azure.Client, args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(stderr, "pim requires a subcommand: list, activate")
		return 2
	}
	tenant := valueFlag(args, "--tenant")
	scope := valueFlag(args, "--scope")
	switch args[0] {
	case "list":
		if scope == "" {
			return fail(stderr, errors.New("pim list requires --scope"))
		}
		roles, err := client.EligibleRoles(ctx, tenant, scope)
		if err != nil {
			return fail(stderr, err)
		}
		for _, r := range roles {
			fmt.Fprintf(stdout, "%s\t%s\n", r.Name, r.ScopeDisplay)
		}
		return 0
	case "activate":
		roleName := valueFlag(args, "--role")
		justification := valueFlag(args, "--justification")
		if scope == "" || roleName == "" {
			return fail(stderr, errors.New("pim activate requires --scope and --role"))
		}
		roles, err := client.EligibleRoles(ctx, tenant, scope)
		if err != nil {
			return fail(stderr, err)
		}
		for _, r := range roles {
			if strings.EqualFold(r.Name, roleName) {
				res, err := client.ActivateRole(ctx, tenant, r.Name, azure.ActivationRequest{
					Scope: r.Scope, RoleDefinitionID: r.RoleDefinitionID,
					PrincipalID: r.PrincipalID, Justification: justification, DurationHours: 4,
				})
				if err != nil {
					return fail(stderr, err)
				}
				fmt.Fprintf(stdout, "%s\t%s\n", res.RoleName, res.Status)
				return 0
			}
		}
		return fail(stderr, fmt.Errorf("no eligible role %q at %s", roleName, scope))
	default:
		fmt.Fprintf(stderr, "unknown pim subcommand %q\n", args[0])
		return 2
	}
}

func valueFlag(args []string, name string) string {
	for i, a := range args {
		if a == name && i+1 < len(args) {
			return args[i+1]
		}
		if strings.HasPrefix(a, name+"=") {
			return strings.TrimPrefix(a, name+"=")
		}
	}
	return ""
}

func fail(stderr io.Writer, err error) int {
	fmt.Fprintln(stderr, "error:", err)
	return 1
}

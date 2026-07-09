import { Body1, Button, Spinner, Title1 } from '@fluentui/react-components';
import { useAuthStatus, useSignOut } from './lib/auth';
import { SignInScreen } from './SignInScreen';

function AuthenticatedShell() {
  const { data } = useAuthStatus();
  const signOut = useSignOut();

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        gap: '8px',
      }}
    >
      <Title1>BlueBridge</Title1>
      <Body1>Signed in as {data?.account.username || data?.account.name}</Body1>
      <Button onClick={() => signOut.mutate()} disabled={signOut.isPending}>
        Sign out
      </Button>
    </main>
  );
}

function App() {
  const { data, isLoading, isError } = useAuthStatus();

  if (isLoading) {
    return (
      <main style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <Spinner label="Connecting to local server…" />
      </main>
    );
  }

  if (isError) {
    return (
      <main style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <Body1>Could not reach the local BlueBridge server.</Body1>
      </main>
    );
  }

  return data?.signedIn ? <AuthenticatedShell /> : <SignInScreen />;
}

export default App;

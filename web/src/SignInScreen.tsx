import { useState } from 'react';
import {
  Body1,
  Button,
  Card,
  Caption1,
  Spinner,
  Subtitle1,
  Text,
  Title1,
  Link,
} from '@fluentui/react-components';
import { getStartupTenantHint } from './lib/apiClient';
import { useSignIn } from './lib/auth';
import { useDeviceCodeEvents } from './lib/useDeviceCodeEvents';
import type { SignInMethod } from './lib/auth';

export function SignInScreen() {
  const signIn = useSignIn();
  const [method, setMethod] = useState<SignInMethod | null>(null);
  const devicePrompt = useDeviceCodeEvents(method === 'devicecode' && signIn.isPending);

  function start(method: SignInMethod) {
    setMethod(method);
    signIn.mutate({ tenantId: getStartupTenantHint(), method });
  }

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        gap: '16px',
      }}
    >
      <Title1>BlueBridge</Title1>
      <Body1>Sign in with your Microsoft account to browse your Azure estate and manage PIM.</Body1>

      <Card style={{ padding: '24px', width: '360px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <Button appearance="primary" disabled={signIn.isPending} onClick={() => start('browser')}>
          Sign in with browser
        </Button>
        <Button disabled={signIn.isPending} onClick={() => start('devicecode')}>
          Sign in with device code
        </Button>
        <Button disabled={signIn.isPending} onClick={() => start('azurecli')}>
          Reuse Azure CLI login
        </Button>

        {signIn.isPending && method !== 'devicecode' && (
          <Spinner label="Waiting for sign-in to complete in your browser…" />
        )}

        {signIn.isPending && method === 'devicecode' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
            {devicePrompt ? (
              <>
                <Subtitle1>{devicePrompt.userCode}</Subtitle1>
                <Link href={devicePrompt.verificationUrl} target="_blank" rel="noreferrer">
                  {devicePrompt.verificationUrl}
                </Link>
                <Caption1>{devicePrompt.message}</Caption1>
              </>
            ) : (
              <Spinner label="Requesting a device code…" />
            )}
          </div>
        )}

        {signIn.isError && <Text style={{ color: 'var(--colorPaletteRedForeground1)' }}>{signIn.error.message}</Text>}
      </Card>
    </main>
  );
}

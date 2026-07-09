import { useQuery } from '@tanstack/react-query';
import { Spinner, Text, Title1 } from '@fluentui/react-components';
import { apiFetch } from './lib/apiClient';

interface VersionResponse {
  version: string;
}

function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['version'],
    queryFn: () => apiFetch<VersionResponse>('/version'),
  });

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
      {isLoading && <Spinner label="Connecting to local server…" />}
      {isError && <Text>Could not reach the local BlueBridge server.</Text>}
      {data && <Text>Server version {data.version}</Text>}
    </main>
  );
}

export default App;

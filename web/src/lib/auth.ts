import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './apiClient';

export interface Account {
  username: string;
  name: string;
  homeTenantId: string;
}

export interface AuthStatus {
  signedIn: boolean;
  account: Account;
}

export type SignInMethod = 'browser' | 'devicecode' | 'azurecli';

const AUTH_STATUS_KEY = ['auth', 'status'];

export function useAuthStatus() {
  return useQuery({
    queryKey: AUTH_STATUS_KEY,
    queryFn: () => apiFetch<AuthStatus>('/auth/status'),
  });
}

export function useSignIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (opts: { tenantId?: string; method?: SignInMethod }) =>
      apiFetch<AuthStatus>('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenantId: opts.tenantId ?? '', method: opts.method ?? 'browser' }),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(AUTH_STATUS_KEY, data);
    },
  });
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>('/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      queryClient.setQueryData(AUTH_STATUS_KEY, { signedIn: false, account: {} });
    },
  });
}

import { useEffect, useState } from 'react';
import { eventsUrl } from './apiClient';

export interface DeviceCodePrompt {
  userCode: string;
  verificationUrl: string;
  message: string;
}

/** Subscribes to the SSE /events stream and surfaces the latest device-code prompt, if any. */
export function useDeviceCodeEvents(active: boolean): DeviceCodePrompt | null {
  const [prompt, setPrompt] = useState<DeviceCodePrompt | null>(null);

  useEffect(() => {
    if (!active) {
      setPrompt(null);
      return;
    }
    const source = new EventSource(eventsUrl());
    source.addEventListener('auth.devicecode', (e: MessageEvent<string>) => {
      setPrompt(JSON.parse(e.data) as DeviceCodePrompt);
    });
    return () => source.close();
  }, [active]);

  return prompt;
}

import { useState, useEffect, useRef } from 'react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '') || '';

type DockerStatus = 'checking' | 'online' | 'offline';

export function useMCPHealth() {
    const [dockerStatus, setDockerStatus] = useState<DockerStatus>('checking');
    const failCountRef = useRef(0);
    const lastOnlineAtRef = useRef<number | null>(null);

    useEffect(() => {
        let cancelled = false;
        const check = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/mcp/health`);
                const data = await res.json();
                if (cancelled) return;
                if (data?.status === 'ok') {
                    failCountRef.current = 0;
                    lastOnlineAtRef.current = Date.now();
                    setDockerStatus('online');
                } else {
                    throw new Error('mcp health not ok');
                }
            } catch {
                if (cancelled) return;
                failCountRef.current += 1;
                if (failCountRef.current >= 3) {
                    setDockerStatus('offline');
                }
            }
        };
        check();
        const timer = setInterval(check, 10000);
        return () => { cancelled = true; clearInterval(timer); };
    }, []);

    /** Reset fail count to zero when we know a run is in progress (don't spam offline) */
    const markRunStarting = () => {
        setDockerStatus('checking');
        failCountRef.current = 0;
    };

    return { dockerStatus, markRunStarting };
}

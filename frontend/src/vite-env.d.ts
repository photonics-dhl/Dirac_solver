/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
    readonly VITE_ENABLE_DEVFLOW?: string;
    readonly VITE_OCTOPUS_INTERACTIVE_FASTPATH?: string;
    readonly VITE_SOLVE_CONNECT_TIMEOUT_MS?: string;
    readonly VITE_SOLVE_STALL_TIMEOUT_MS?: string;
    readonly VITE_SOLVE_HARD_TIMEOUT_MS?: string;
    readonly VITE_OCTOPUS_AUTOREVIEWER?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}

import React from 'react';

interface Props { children: React.ReactNode; fallback?: React.ReactNode }
interface State { hasError: boolean; message: string }

export class ErrorBoundary extends React.Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, message: '' };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, message: error?.message || 'Unknown error' };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error('[ErrorBoundary]', error, info.componentStack);
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) return this.props.fallback;
            return (
                <div className="m-4 p-4 rounded-lg border border-red-500/30 bg-red-950/25 text-red-200 text-sm">
                    <div className="font-semibold mb-1">Something went wrong</div>
                    <div className="text-red-300/70 font-mono text-xs">{this.state.message}</div>
                    <button
                        onClick={() => this.setState({ hasError: false, message: '' })}
                        className="mt-2 px-3 py-1 rounded bg-red-500/15 border border-red-500/30 text-red-300 text-xs hover:bg-red-500/25 transition-colors"
                    >
                        Retry
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

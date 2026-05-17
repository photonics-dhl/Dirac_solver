interface Props {
    logs: string[];
    isComputing: boolean;
}

export function RuntimeLog({ logs, isComputing }: Props) {
    return (
        <div className="mt-3 rounded-lg overflow-hidden" style={{ border: '1px solid #1a2035', background: '#060d1a' }}>
            <div className="px-3 py-2 text-[11px] uppercase tracking-widest" style={{ color: '#64748b', borderBottom: '1px solid #1a2035' }}>
                Runtime Log
            </div>
            <div className="max-h-[320px] overflow-auto p-3 font-mono text-[12px] leading-relaxed">
                {logs.map((log, i) => (
                    <div
                        key={i}
                        className={`${
                            log.includes('✗') || log.includes('Error') ? 'text-red-400'
                            : log.includes('✓') || log.includes('SUCCESS') ? 'text-green-400'
                            : log.includes('[System]') ? 'text-blue-400'
                            : 'text-gray-400'
                        } mb-0.5`}
                    >
                        {log}
                    </div>
                ))}
                {isComputing && (
                    <div className="text-gray-500 animate-pulse flex items-center gap-2 mt-2">
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
                        Processing quantum computation...
                    </div>
                )}
            </div>
        </div>
    );
}

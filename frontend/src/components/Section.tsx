import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

export function Section({ title, icon, defaultOpen = true, children }: {
    title: string; icon: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode
}) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="rounded-xl overflow-hidden mb-3" style={{ border: '1px solid #1a2035' }}>
            <button onClick={() => setOpen(!open)}
                className="w-full flex items-center gap-2 px-4 py-3 transition-colors text-left"
                style={{ background: '#0d1525' }}>
                {open ? <ChevronDown className="w-4 h-4" style={{ color: '#8892a4' }} /> : <ChevronRight className="w-4 h-4" style={{ color: '#8892a4' }} />}
                {icon}
                <span className="text-sm font-medium" style={{ color: '#cbd5e1' }}>{title}</span>
            </button>
            {open && <div className="p-4 space-y-3" style={{ background: '#060d1a' }}>{children}</div>}
        </div>
    );
}

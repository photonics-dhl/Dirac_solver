import React from 'react';

export const inputClass = "w-full rounded-lg px-3 py-2 text-sm text-white outline-none transition-colors" +
    " bg-[#0a1220] border border-[#1e2d45] focus:border-[#00d4ff] focus:ring-1 focus:ring-[#00d4ff] focus:ring-opacity-30";
export const selectClass = inputClass;

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
    return (
        <div className="space-y-1">
            <label className="text-xs font-medium" style={{ color: '#8892a4' }}>{label}</label>
            {children}
            {hint && <p className="text-[10px] mt-0.5" style={{ color: '#455060' }}>{hint}</p>}
        </div>
    );
}

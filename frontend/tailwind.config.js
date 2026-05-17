/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                surface: {
                    'main': '#0a0e1a',
                    'card': '#0d1525',
                    'body': '#060d1a',
                    'input': '#0a1220',
                    'hover': '#111827',
                },
                border: {
                    'primary': '#1a2035',
                    'input': '#1e2d45',
                    'review': '#273244',
                },
                accent: {
                    'cyan': '#00d4ff',
                    'purple': '#a855f7',
                },
                text: {
                    'primary': '#e2e8f0',
                    'secondary': '#8892a4',
                    'muted': '#64748b',
                    'light': '#cbd5e1',
                    'soft': '#94a3b8',
                    'hint': '#455060',
                },
            },
        },
    },
    plugins: [],
};

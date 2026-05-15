export const HARTREE_TO_EV = 27.211386245988;

export function parseScanSpec(spec: string): number[] {
    const src = String(spec || '').trim();
    if (!src) return [];

    const parseNums = (content: string) => content.split(',').map((v) => Number(v.trim()));
    const linspaceMatch = src.match(/^linspace\((.+)\)$/i);
    if (linspaceMatch) {
        const nums = parseNums(linspaceMatch[1]);
        if (nums.length !== 3 || nums.some((n) => !Number.isFinite(n))) {
            throw new Error('linspace(...) expects three numeric arguments');
        }
        const [a, b, c] = nums;
        const isCountForm = Math.abs(c - Math.round(c)) < 1e-9 && c >= 2;
        if (isCountForm) {
            const count = Math.floor(c);
            if (count < 2) throw new Error('linspace(start,end,count): count must be >= 2');
            const step = (b - a) / (count - 1);
            return Array.from({ length: count }, (_, i) => a + i * step);
        }
        const start = a;
        const step = b;
        const end = c;
        if (Math.abs(step) < 1e-12) throw new Error('linspace(start,step,end): step must be non-zero');
        if ((end - start) * step < 0) throw new Error('linspace(start,step,end): step direction does not reach end');
        const out: number[] = [];
        let x = start;
        if (step > 0) {
            while (x <= end + 1e-12) {
                out.push(x);
                x += step;
            }
        } else {
            while (x >= end - 1e-12) {
                out.push(x);
                x += step;
            }
        }
        return out;
    }

    const rangeMatch = src.match(/^range\((.+)\)$/i);
    if (rangeMatch) {
        const nums = parseNums(rangeMatch[1]);
        if (nums.length !== 3 || nums.some((n) => !Number.isFinite(n))) {
            throw new Error('range(start,step,end) expects three numeric arguments');
        }
        const [start, step, end] = nums;
        if (Math.abs(step) < 1e-12) throw new Error('range(start,step,end): step must be non-zero');
        if ((end - start) * step < 0) throw new Error('range(start,step,end): step direction does not reach end');
        const out: number[] = [];
        let x = start;
        if (step > 0) {
            while (x <= end + 1e-12) {
                out.push(x);
                x += step;
            }
        } else {
            while (x >= end - 1e-12) {
                out.push(x);
                x += step;
            }
        }
        return out;
    }

    const direct = src
        .split(',')
        .map((v) => Number(v.trim()))
        .filter((n) => Number.isFinite(n));
    if (!direct.length) {
        throw new Error('Scan spec is empty or invalid');
    }
    return direct;
}

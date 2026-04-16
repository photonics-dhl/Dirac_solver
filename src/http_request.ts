import * as http from 'http';
import * as https from 'https';

export interface HttpRequestOptions {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    timeoutMs?: number;
}

export interface HttpResponse {
    status: number;
    ok: boolean;
    text(): Promise<string>;
    json<T = any>(): Promise<T>;
}

export function httpRequest(urlString: string, options: HttpRequestOptions = {}): Promise<HttpResponse> {
    return new Promise((resolve, reject) => {
        const url = new URL(urlString);
        const transport = url.protocol === 'https:' ? https : http;
        const req = transport.request(
            {
                hostname: url.hostname,
                port: url.port || (url.protocol === 'https:' ? 443 : 80),
                path: `${url.pathname}${url.search}`,
                method: options.method ?? 'GET',
                headers: options.headers,
            },
            (res) => {
                const chunks: Buffer[] = [];
                res.on('data', (chunk: Buffer) => chunks.push(chunk));
                res.on('end', () => {
                    const body = Buffer.concat(chunks).toString('utf-8');
                    const status = res.statusCode ?? 0;
                    resolve({
                        status,
                        ok: status >= 200 && status < 300,
                        async text() {
                            return body;
                        },
                        async json<T = any>() {
                            return JSON.parse(body) as T;
                        },
                    });
                });
            }
        );

        req.on('error', reject);

        if (options.timeoutMs && options.timeoutMs > 0) {
            req.setTimeout(options.timeoutMs, () => {
                req.destroy(new Error(`Request timeout after ${options.timeoutMs}ms`));
            });
        }

        if (options.body) {
            req.write(options.body);
        }

        req.end();
    });
}

import os
import socket
import base64
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from openai import OpenAI
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Retrieve API Key and Base URL from environment variables
API_KEY = os.getenv("ZCHAT_API_KEY", "")
BASE_URL = os.getenv("ZCHAT_BASE_URL", "https://api.zchat.tech/v1")


def _is_placeholder_key(value: str) -> bool:
    if not value:
        return True
    v = value.strip().lower()
    return v in {
        "your_key_here",
        "sk-your_key_here",
        "replace_me",
        "changeme",
        "none",
        "null",
    }


def _normalize_base_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "https://api.zchat.tech/v1"
    low = raw.lower()
    if "example.com" in low or "zchat.example.com" in low:
        return "https://api.zchat.tech/v1"
    return raw

# The requested fallback sequence
DEFAULT_MODELS_FALLBACK = [
    "gpt-5",             # 当前zchat主模型
    "gpt-5-thinking",    # 推理增强版本
    "claude-sonnet-4-5", # 失效后回退到claude4.5
    "grok-4"             # 最后回退到grok4
]

class LLMClient:
    def __init__(self, api_key=None, base_url=None, timeout_seconds=45):
        self.api_key = (api_key or API_KEY or "").strip()
        self.base_url = _normalize_base_url(base_url or BASE_URL)
        self.timeout_seconds = timeout_seconds
        self.last_diagnostics = {}

        if _is_placeholder_key(self.api_key):
            raise ValueError("ZCHAT_API_KEY 未配置或仍为占位值（your_key_here），请填写真实密钥")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,
        )

    def preflight_check(self):
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "api.zchat.tech"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or ""
        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or ""
        active_proxy = https_proxy or http_proxy
        diagnostics = {
            "base_url": self.base_url,
            "host": host,
            "port": port,
            "proxy": active_proxy,
            "dns_ok": False,
            "tcp_ok": False,
            "https_ok": False,
            "http_status": None,
            "error": "",
        }

        if active_proxy:
            proxy_parsed = urlparse(active_proxy)
            proxy_host = proxy_parsed.hostname
            proxy_port = proxy_parsed.port or (443 if proxy_parsed.scheme == "https" else 80)
            diagnostics["proxy_host"] = proxy_host
            diagnostics["proxy_port"] = proxy_port
            if not proxy_host:
                diagnostics["error"] = "PROXY_PARSE_FAIL: invalid proxy URL"
                self.last_diagnostics = diagnostics
                return diagnostics
            s = socket.socket()
            s.settimeout(8)
            try:
                s.connect((proxy_host, proxy_port))
                diagnostics["tcp_ok"] = True
            except Exception as e:
                diagnostics["error"] = f"PROXY_TCP_FAIL: {e}"
                self.last_diagnostics = diagnostics
                return diagnostics
            finally:
                try:
                    s.close()
                except Exception:
                    pass
            try:
                req = Request(self.base_url, method="GET")
                with urlopen(req, timeout=10) as resp:
                    diagnostics["https_ok"] = True
                    diagnostics["http_status"] = getattr(resp, "status", None)
            except Exception as e:
                # HTTPError like 401 means endpoint reachable
                msg = str(e)
                if "401" in msg or "403" in msg:
                    diagnostics["https_ok"] = True
                    diagnostics["http_status"] = int("401" if "401" in msg else "403")
                else:
                    diagnostics["error"] = f"HTTPS_FAIL_VIA_PROXY: {e}"
            self.last_diagnostics = diagnostics
            return diagnostics

        try:
            socket.gethostbyname(host)
            diagnostics["dns_ok"] = True
        except Exception as e:
            diagnostics["error"] = f"DNS_FAIL: {e}"
            self.last_diagnostics = diagnostics
            return diagnostics

        s = socket.socket()
        s.settimeout(8)
        try:
            s.connect((host, port))
            diagnostics["tcp_ok"] = True
        except Exception as e:
            diagnostics["error"] = f"TCP_FAIL: {e}"
            self.last_diagnostics = diagnostics
            return diagnostics
        finally:
            try:
                s.close()
            except Exception:
                pass

        try:
            req = Request(self.base_url, method="GET")
            with urlopen(req, timeout=10) as resp:
                diagnostics["https_ok"] = True
                diagnostics["http_status"] = getattr(resp, "status", None)
        except Exception as e:
            diagnostics["error"] = f"HTTPS_FAIL: {e}"

        self.last_diagnostics = diagnostics
        return diagnostics

    def build_multimodal_user_message(self, text, image_paths=None, image_urls=None):
        content = [{"type": "text", "text": text}]

        for p in (image_paths or []):
            if not p or not os.path.exists(p):
                continue
            try:
                ext = os.path.splitext(p)[1].lower().replace(".", "") or "png"
                if ext == "jpg":
                    ext = "jpeg"
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:image/{ext};base64,{b64}"
                content.append({"type": "image_url", "image_url": {"url": data_url}})
            except Exception:
                continue

        for u in (image_urls or []):
            if not u:
                continue
            content.append({"type": "image_url", "image_url": {"url": u}})

        return {"role": "user", "content": content}

    def chat_completion(self, messages, models=None, **kwargs):
        """
        Call the chat completion API with model fallback.
        
        Note: Since it's a reverse API, temperature, max_tokens, etc. parameters are not supported.
        Hence, we avoid passing them to prevent errors unless explicitly given in kwargs.
        """
        if models is None:
            models = DEFAULT_MODELS_FALLBACK
            
        last_exception = None
        for model in models:
            try:
                print(f"[*] 尝试使用模型: {model} ...")
                # Remove temperature/max_tokens from kwargs if they present as unsupported by reverse API
                kwargs.pop("temperature", None)
                kwargs.pop("max_tokens", None)
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=False,
                    **kwargs
                )
                print(f"[+] 成功从 {model} 获取响应！")
                return response
            except Exception as e:
                print(f"[-] 模型 {model} 调用失败: {str(e)}")
                last_exception = e
                
        diag = self.preflight_check()
        raise Exception(
            f"所有回退模型都已失效，最后一次错误: {str(last_exception)} | "
            f"diag={{dns_ok:{diag.get('dns_ok')}, tcp_ok:{diag.get('tcp_ok')}, https_ok:{diag.get('https_ok')}, error:{diag.get('error')}}}"
        )

# Usage example
if __name__ == "__main__":
    print("=== 开始测试ZCHAT大模型API (带回退机制) ===")
    
    test_messages = [
        {"role": "developer", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "你好，请介绍一下自己。"}
    ]
    
    # Instantiate client
    llm = LLMClient()
    
    try:
        reply = llm.chat_completion(test_messages)
        print("\n最终响应结果:")
        print("Assistant:", reply.choices[0].message.content)
    except Exception as e:
        print(f"\n[!] 最终调用失败: {str(e)}")

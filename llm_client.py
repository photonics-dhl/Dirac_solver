import os
from openai import OpenAI
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Retrieve API Key and Base URL from environment variables, fallback to defaults if not found
API_KEY = os.getenv("ZCHAT_API_KEY", "sk-uK1cqmlDbsRaUyNS2lkcUGC6FRewPLUZ7GWbEvjrhDMzM6Rf")
# The images specify a few possible correct endpoints, we use the standard chat completions base path.
BASE_URL = os.getenv("ZCHAT_BASE_URL", "https://api.zchat.tech/v1")

# The requested fallback sequence
DEFAULT_MODELS_FALLBACK = [
    "gpt-5-2",           # 优先调用zchat支持的gpt5.2
    "gemini-3-pro",      # 失效后回退到gemini3pro
    "claude-sonnet-4-5", # 失效后回退到claude4.5
    "grok-4"             # 最后回退到grok4
]

class LLMClient:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or API_KEY
        self.base_url = base_url or BASE_URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

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
                
        raise Exception(f"所有回退模型都已失效，最后一次错误: {str(last_exception)}")

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

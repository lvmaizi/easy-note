import requests

from src.config import LLMConfig


class LLMClient:
    # 单次请求超时（秒）。过长会让"停止"按钮等很久，过短会截断长回答。
    REQUEST_TIMEOUT = 120

    def __init__(self, config: LLMConfig):
        self.config = config

    def chat(self, messages: list[dict]) -> str:
        if not self.config.api_url or not self.config.api_key:
            raise RuntimeError("请先在「⚙ 设置」中填写模型地址与 API 密钥")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        try:
            resp = requests.post(
                self.config.api_url,
                headers=headers,
                json=body,
                timeout=self.REQUEST_TIMEOUT,
            )
        except requests.exceptions.MissingSchema:
            raise RuntimeError("模型地址无效，请在「⚙ 设置」中检查 api_url 是否完整（需含 https://）")
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接到 LLM API，请检查网络和 api_url 配置")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"LLM API 请求超时（{self.REQUEST_TIMEOUT}s），请稍后重试")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"LLM 请求失败：{e}") from e

        # 状态码映射为固定文案，避免把上游响应体（可能含密钥片段）原样回显给用户
        if resp.status_code == 401:
            raise RuntimeError("API 密钥无效或未授权，请在「⚙ 设置」中检查密钥")
        if resp.status_code == 429:
            raise RuntimeError("LLM API 限流，请稍后重试")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"LLM API 返回错误（HTTP {resp.status_code}），请检查模型地址与模型名是否匹配"
            )

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError("LLM 返回了无法解析的响应，请检查模型与接口是否 OpenAI 兼容") from e

        # 个别接口在 finish_reason=length / content_filter 时返回 null content
        if content is None:
            return ""
        return content

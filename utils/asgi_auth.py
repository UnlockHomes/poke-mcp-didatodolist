"""
简单的 ASGI 中间件：为 SSE 入口添加 x-api-key 鉴权，并支持路径重写。
当前 fastmcp 版本不支持 authenticate 参数时，可通过该中间件实现最小可用的 Header 鉴权。
支持将 /mcp 路径重写为 fastmcp 的实际端点（如 /sse）。
"""

from typing import Callable, Awaitable
import os


class ApiKeyAuthMiddleware:
    def __init__(self, app, header_name: str = "x-api-key", expected_key: str | None = None, 
                 sse_path: str = "/mcp", rewrite_to: str | None = None):
        self.app = app
        self.header_name = header_name.lower()
        self.expected_key = expected_key or os.environ.get("MCP_API_KEY", "123")
        self.sse_path = sse_path
        # 如果指定了 rewrite_to，将请求路径从 sse_path 重写为 rewrite_to
        # 例如：/mcp -> /sse
        self.rewrite_to = rewrite_to

    async def __call__(self, scope, receive, send):
        # 仅对 HTTP scope 且 SSE 路径做校验，其余直接放行
        if scope.get("type") == "http":
            path = scope.get("path", "")
            # 检查是否是目标路径（可能是原始路径或重写后的路径）
            if path.startswith(self.sse_path) or (self.rewrite_to and path.startswith(self.rewrite_to)):
                # 提取 header（bytes）
                headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
                api_key = headers.get(self.header_name)
                if api_key != self.expected_key:
                    body = b"Unauthorized: missing or invalid x-api-key"
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": body,
                        "more_body": False,
                    })
                    return
                
                # 如果需要路径重写（例如 /mcp -> /sse）
                if self.rewrite_to and path.startswith(self.sse_path):
                    # 重写路径
                    new_path = path.replace(self.sse_path, self.rewrite_to, 1)
                    scope = dict(scope)
                    scope["path"] = new_path
                    scope["raw_path"] = new_path.encode("latin1")
        
        return await self.app(scope, receive, send)


def with_api_key_auth(app, header_name: str = "x-api-key", expected_key: str | None = None, 
                      sse_path: str = "/mcp", rewrite_to: str | None = None):
    """
    创建带 API Key 鉴权的 ASGI 中间件
    
    Args:
        app: ASGI 应用
        header_name: API Key 的请求头名称
        expected_key: 期望的 API Key 值
        sse_path: 对外暴露的路径（如 /mcp）
        rewrite_to: 内部实际路径（如 /sse），如果为 None 则不重写
    """
    return ApiKeyAuthMiddleware(app, header_name=header_name, expected_key=expected_key, 
                               sse_path=sse_path, rewrite_to=rewrite_to)

#!/usr/bin/env python
"""
滴答清单 MCP 服务入口点
允许AI模型通过MCP协议访问和操作滴答清单待办事项
"""

import os
import sys
import argparse
import json
from pathlib import Path
import dotenv
from tools.official_api import init_api

# 加载环境变量（支持 .env）
dotenv.load_dotenv()

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="滴答清单 MCP 服务"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="安装到Claude Desktop或其他MCP客户端"
    )
    parser.add_argument(
        "--token",
        help="滴答清单访问令牌"
    )
    parser.add_argument(
        "--email",
        help="滴答清单账户邮箱"
    )
    parser.add_argument(
        "--phone",
        help="滴答清单账户手机号"
    )
    parser.add_argument(
        "--password",
        help="滴答清单账户密码"
    )
    # 统一 .env-only，不再支持 config 文件路径
    # 支持 Railway 部署：从 PORT 环境变量读取端口
    default_port = int(os.environ.get("PORT", 3000))
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="服务器端口号（用于SSE传输方式，默认从PORT环境变量读取）"
    )
    # Railway 部署需要监听 0.0.0.0
    default_host = os.environ.get("HOST", "0.0.0.0")
    parser.add_argument(
        "--host",
        default=default_host,
        help="服务器主机（用于SSE传输方式，默认0.0.0.0以支持Railway部署）"
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="使用SSE传输方式而不是stdio"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="使用HTTP模式（FastAPI），用于Railway等云端部署"
    )

    return parser.parse_args()

def ensure_oauth_ready() -> bool:
    """仅使用 .env 初始化官方API。"""
    try:
        init_api()
        return True
    except Exception as e:
        print("未检测到有效的 OAuth access_token。")
        print("请先运行 OAuth 认证脚本：")
        print("  python scripts/oauth_authenticate.py --port 38000")
        print("脚本会将 DIDA_ACCESS_TOKEN / DIDA_REFRESH_TOKEN 写入 .env，然后再启动本服务。")
        print(f"详情: {e}")
        return False

def main():
    """主函数"""
    args = parse_args()
    
    # HTTP 模式直接启动 FastAPI，不需要 FastMCP
    if args.http:
        # 使用HTTP模式（FastAPI）
        print("启动滴答清单MCP服务器（HTTP模式）...")
        import uvicorn
        from http_server import app
        uvicorn.run(app, host=args.host, port=args.port)
        return
    
    # 非 HTTP 模式才需要 FastMCP
    # 延迟导入，避免在 HTTP 模式下加载 FastMCP
    from mcp_server import create_server
    
    if not ensure_oauth_ready():
        # 不中止运行，允许用户仅安装/查看说明
        pass

    # 创建MCP服务器
    server = create_server({})

    # 启动服务器
    if args.install:
        # 安装到Claude Desktop
        print("正在安装到MCP客户端...")
        os.system("fastmcp install")
    else:
        # 直接运行
        print("启动滴答清单MCP服务器...")
        if args.sse:
            # 使用SSE传输方式，路径设置为 /mcp 以兼容 Poke
            # fastmcp 的 run 方法可能支持 path 参数，如果不支持则通过中间件处理
            try:
                server.run(transport="sse", host=args.host, port=args.port, path="/mcp")
            except TypeError:
                # 如果不支持 path 参数，使用默认路径，中间件会处理 /mcp 路径
                server.run(transport="sse", host=args.host, port=args.port)
        else:
            # 使用默认stdio传输方式
            print("使用stdio传输方式")
            server.run()

if __name__ == "__main__":
    main()
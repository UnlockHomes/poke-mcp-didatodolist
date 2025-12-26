"""
HTTP Server wrapper for MCP DidaTodoList Server
This allows the MCP server to be accessed via HTTP/HTTPS for Railway deployment
"""
import json
import asyncio
import os
import sys
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from mcp.types import Tool
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Import API initialization
from tools.official_api import init_api

# Import logic functions directly
from tools.task_tools import (
    get_tasks_logic,
    create_task_logic,
    update_task_logic,
    delete_task_logic,
    complete_task_logic
)
from tools.project_tools import (
    get_projects_logic,
    create_project_logic,
    update_project_logic,
    delete_project_logic
)
from tools.tag_tools import register_tag_tools
from tools.adapter import adapter
from tools.goal_tools import (
    create_goal_logic,
    get_goals_logic,
    update_goal_logic,
    delete_goal_logic,
    match_task_with_goals_logic
)
from tools.analytics_tools import AnalyticsManager

app = FastAPI(title="DidaTodoList MCP Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize API (OAuth)
# 在 Railway 中，环境变量通过 Railway Variables 设置，不需要 .env 文件
try:
    init_api()
    print("已初始化官方API 客户端")
except Exception as e:
    print(f"警告：未能初始化官方API：{e}")
    print("请确保在 Railway Variables 中设置了以下环境变量：")
    print("  - DIDA_CLIENT_ID")
    print("  - DIDA_CLIENT_SECRET")
    print("  - DIDA_ACCESS_TOKEN")

# Initialize analytics manager
analytics_manager = AnalyticsManager()

# API Key authentication
# 从环境变量读取，Railway 会通过 Variables 设置
API_KEY = os.environ.get("MCP_API_KEY")
if not API_KEY:
    print("警告：MCP_API_KEY 环境变量未设置，将使用默认值（不安全）")
    API_KEY = "123"  # 默认值，仅用于开发

# Debug endpoint to check if API_KEY is loaded (remove in production)
@app.get("/debug/api-key")
async def debug_api_key():
    """Debug endpoint to check if API_KEY is loaded"""
    return {
        "api_key_set": bool(API_KEY),
        "api_key_length": len(API_KEY) if API_KEY else 0,
        "api_key_preview": API_KEY[:10] + "..." if API_KEY and len(API_KEY) > 10 else (API_KEY if API_KEY else None)
    }

def verify_api_key(request: Request) -> bool:
    """Verify API key from request headers"""
    # If no API key is set, allow all requests (backward compatible)
    if not API_KEY:
        return True
    
    # Check for API key in headers
    # Poke sends it as Authorization: Bearer <key> or X-API-Key header
    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")
    x_api_key_header = request.headers.get("x-api-key", "")
    
    # Extract token from Bearer format
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
    elif api_key_header:
        token = api_key_header.strip()
    elif x_api_key_header:
        token = x_api_key_header.strip()
    
    if not token:
        return False
    
    return token == API_KEY

# Tool definitions for MCP protocol
def get_tool_definitions():
    """List available DidaTodoList tools."""
    tools = [
        # Task tools
        Tool(
            name="get_tasks",
            description="获取任务列表，支持多种筛选条件",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "任务模式，支持 'all'(所有), 'today'(今天), 'yesterday'(昨天), 'recent_7_days'(最近7天)",
                        "default": "all"
                    },
                    "keyword": {"type": "string", "description": "关键词筛选"},
                    "priority": {"type": "integer", "description": "优先级筛选 (0-最低, 1-低, 3-中, 5-高)"},
                    "project_name": {"type": "string", "description": "项目名称筛选"},
                    "completed": {"type": "boolean", "description": "是否已完成"}
                }
            }
        ),
        Tool(
            name="create_task",
            description="创建新任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任务标题"},
                    "content": {"type": "string", "description": "任务内容"},
                    "priority": {"type": "integer", "description": "优先级 (0-最低, 1-低, 3-中, 5-高)"},
                    "project_name": {"type": "string", "description": "项目名称"},
                    "tag_names": {"type": "array", "items": {"type": "string"}, "description": "标签名称列表"},
                    "start_date": {"type": "string", "description": "开始日期 (YYYY-MM-DD)"},
                    "due_date": {"type": "string", "description": "截止日期 (YYYY-MM-DD)"},
                    "is_all_day": {"type": "boolean", "description": "是否全天"},
                    "reminder": {"type": "string", "description": "提醒时间"}
                }
            }
        ),
        Tool(
            name="update_task",
            description="更新任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id_or_title": {"type": "string", "description": "任务ID或标题"},
                    "title": {"type": "string", "description": "新标题"},
                    "content": {"type": "string", "description": "新内容"},
                    "priority": {"type": "integer", "description": "优先级"},
                    "project_name": {"type": "string", "description": "项目名称"},
                    "due_date": {"type": "string", "description": "截止日期"}
                },
                "required": ["task_id_or_title"]
            }
        ),
        Tool(
            name="delete_task",
            description="删除任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id_or_title": {"type": "string", "description": "任务ID或标题"}
                },
                "required": ["task_id_or_title"]
            }
        ),
        Tool(
            name="complete_task",
            description="完成任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id_or_title": {"type": "string", "description": "任务ID或标题"}
                },
                "required": ["task_id_or_title"]
            }
        ),
        # Project tools
        Tool(
            name="get_projects",
            description="获取所有项目列表",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="create_project",
            description="创建新项目",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "项目名称"},
                    "color": {"type": "string", "description": "项目颜色，如 '#FF0000'"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="update_project",
            description="更新项目",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id_or_name": {"type": "string", "description": "项目ID或名称"},
                    "name": {"type": "string", "description": "新名称"},
                    "color": {"type": "string", "description": "新颜色"}
                },
                "required": ["project_id_or_name"]
            }
        ),
        Tool(
            name="delete_project",
            description="删除项目",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id_or_name": {"type": "string", "description": "项目ID或名称"}
                },
                "required": ["project_id_or_name"]
            }
        ),
        # Tag tools
        Tool(
            name="get_tags",
            description="获取所有标签列表",
            inputSchema={"type": "object", "properties": {}}
        ),
        # Goal tools
        Tool(
            name="create_goal",
            description="创建新目标",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "目标标题"},
                    "type": {"type": "string", "description": "目标类型 (phase/permanent/habit)", "enum": ["phase", "permanent", "habit"]},
                    "keywords": {"type": "string", "description": "关键词，以逗号分隔"},
                    "description": {"type": "string", "description": "目标描述"},
                    "due_date": {"type": "string", "description": "截止日期 (YYYY-MM-DD)"},
                    "start_date": {"type": "string", "description": "开始日期 (YYYY-MM-DD)"},
                    "frequency": {"type": "string", "description": "频率 (daily, weekly:1,3,5 等)"}
                },
                "required": ["title", "type", "keywords"]
            }
        ),
        Tool(
            name="get_goals",
            description="获取目标列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "目标类型筛选"},
                    "status": {"type": "string", "description": "状态筛选"},
                    "keywords": {"type": "string", "description": "关键词筛选"}
                }
            }
        ),
        Tool(
            name="update_goal",
            description="更新目标",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string", "description": "目标ID"},
                    "title": {"type": "string", "description": "新标题"},
                    "keywords": {"type": "string", "description": "新关键词"},
                    "description": {"type": "string", "description": "新描述"}
                },
                "required": ["goal_id"]
            }
        ),
        Tool(
            name="delete_goal",
            description="删除目标",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string", "description": "目标ID"}
                },
                "required": ["goal_id"]
            }
        ),
        Tool(
            name="match_task_with_goals",
            description="匹配任务与目标",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_title": {"type": "string", "description": "任务标题"},
                    "task_content": {"type": "string", "description": "任务内容"},
                    "min_score": {"type": "number", "description": "最小匹配分数", "default": 0.3}
                },
                "required": ["task_title"]
            }
        ),
        # Analytics tools
        Tool(
            name="get_goal_statistics",
            description="获取目标统计信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "force_refresh": {"type": "boolean", "description": "是否强制刷新缓存", "default": False}
                }
            }
        ),
        Tool(
            name="get_task_statistics",
            description="获取任务统计信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "统计天数", "default": 30},
                    "force_refresh": {"type": "boolean", "description": "是否强制刷新缓存", "default": False}
                }
            }
        ),
        Tool(
            name="generate_weekly_summary",
            description="生成周报",
            inputSchema={
                "type": "object",
                "properties": {
                    "force_refresh": {"type": "boolean", "description": "是否强制刷新缓存", "default": False}
                }
            }
        ),
    ]
    return tools

async def call_tool(name: str, arguments: dict):
    """Handle tool calls for DidaTodoList API."""
    try:
        # Task tools
        if name == "get_tasks":
            return get_tasks_logic(
                mode=arguments.get("mode", "all"),
                keyword=arguments.get("keyword"),
                priority=arguments.get("priority"),
                project_name=arguments.get("project_name"),
                completed=arguments.get("completed")
            )
        elif name == "create_task":
            return create_task_logic(
                title=arguments.get("title"),
                content=arguments.get("content"),
                priority=arguments.get("priority"),
                project_name=arguments.get("project_name"),
                tag_names=arguments.get("tag_names"),
                start_date=arguments.get("start_date"),
                due_date=arguments.get("due_date"),
                is_all_day=arguments.get("is_all_day"),
                reminder=arguments.get("reminder")
            )
        elif name == "update_task":
            return update_task_logic(
                task_id_or_title=arguments.get("task_id_or_title"),
                title=arguments.get("title"),
                content=arguments.get("content"),
                priority=arguments.get("priority"),
                project_name=arguments.get("project_name"),
                due_date=arguments.get("due_date")
            )
        elif name == "delete_task":
            return delete_task_logic(arguments.get("task_id_or_title"))
        elif name == "complete_task":
            return complete_task_logic(arguments.get("task_id_or_title"))
        
        # Project tools
        elif name == "get_projects":
            return get_projects_logic()
        elif name == "create_project":
            return create_project_logic(
                name=arguments.get("name"),
                color=arguments.get("color")
            )
        elif name == "update_project":
            return update_project_logic(
                project_id_or_name=arguments.get("project_id_or_name"),
                name=arguments.get("name"),
                color=arguments.get("color")
            )
        elif name == "delete_project":
            return delete_project_logic(arguments.get("project_id_or_name"))
        
        # Tag tools
        elif name == "get_tags":
            # get_tags is implemented inline in the tool, so we replicate the logic
            try:
                tasks = adapter.list_tasks()
            except Exception:
                tasks = []
            agg: dict[str, dict] = {}
            for t in tasks or []:
                for tag_name in t.get('tags', []) or []:
                    if tag_name not in agg:
                        agg[tag_name] = {"name": tag_name, "label": tag_name}
            return list(agg.values())
        
        # Goal tools
        elif name == "create_goal":
            return create_goal_logic(
                title=arguments.get("title"),
                type=arguments.get("type"),
                keywords=arguments.get("keywords"),
                description=arguments.get("description"),
                due_date=arguments.get("due_date"),
                start_date=arguments.get("start_date"),
                frequency=arguments.get("frequency")
            )
        elif name == "get_goals":
            return get_goals_logic(
                type=arguments.get("type"),
                status=arguments.get("status"),
                keywords=arguments.get("keywords")
            )
        elif name == "update_goal":
            return update_goal_logic(
                goal_id=arguments.get("goal_id"),
                title=arguments.get("title"),
                keywords=arguments.get("keywords"),
                description=arguments.get("description")
            )
        elif name == "delete_goal":
            return delete_goal_logic(arguments.get("goal_id"))
        elif name == "match_task_with_goals":
            return match_task_with_goals_logic(
                task_title=arguments.get("task_title"),
                task_content=arguments.get("task_content"),
                min_score=arguments.get("min_score", 0.3)
            )
        
        # Analytics tools
        elif name == "get_goal_statistics":
            return analytics_manager.get_goal_statistics(
                force_refresh=arguments.get("force_refresh", False)
            )
        elif name == "get_task_statistics":
            return analytics_manager.get_task_statistics(
                days=arguments.get("days", 30),
                force_refresh=arguments.get("force_refresh", False)
            )
        elif name == "generate_weekly_summary":
            return analytics_manager.generate_weekly_summary(
                force_refresh=arguments.get("force_refresh", False)
            )
        
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    except Exception as e:
        raise ValueError(f"Error processing tool call '{name}': {str(e)}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "DidaTodoList MCP Server"}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP protocol endpoint - JSON-RPC 2.0"""
    # Verify API key if configured
    if API_KEY and not verify_api_key(request):
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32001,
                    "message": "Unauthorized: Invalid or missing API key"
                }
            }
        )
    
    try:
        body = await request.json()
        
        # Handle MCP protocol messages
        if body.get("jsonrpc") == "2.0":
            method = body.get("method")
            params = body.get("params", {})
            
            if method == "tools/list":
                tools = get_tool_definitions()
                # Fix null fields for MCP Inspector compatibility
                tools_list = []
                for tool in tools:
                    tool_dict = tool.model_dump()
                    # Remove null fields or provide defaults
                    for key in ["title", "icons", "outputSchema", "annotations", "execution", "meta"]:
                        if tool_dict.get(key) is None:
                            tool_dict.pop(key, None)
                    tools_list.append(tool_dict)
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "tools": tools_list
                    }
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await call_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, default=str, indent=2, ensure_ascii=False)
                            }
                        ]
                    }
                }
            elif method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "didatodolist-mcp",
                            "version": "0.1.0"
                        }
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
        else:
            return {"error": "Invalid JSON-RPC request"}
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in locals() else None,
            "error": {"code": -32603, "message": str(e)}
        }

@app.get("/tools")
async def list_tools_endpoint():
    """List all available tools"""
    tools = get_tool_definitions()
    return {
        "tools": [tool.model_dump() for tool in tools]
    }

@app.get("/mcp")
async def mcp_sse_endpoint(request: Request):
    """MCP Streamable HTTP endpoint using Server-Sent Events"""
    async def event_stream():
        # Send initial connection message
        yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'connection/opened'})}\n\n"
        
        # For SSE, we need to handle incoming messages via POST to a separate endpoint
        # This is a simplified version - full SSE implementation would require bidirectional communication
        # For now, we'll just keep the connection open
        while True:
            await asyncio.sleep(1)
            # Keep connection alive
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)


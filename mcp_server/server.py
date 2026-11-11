"""用官方 MCP SDK 暴露 DuReader 搜索和段落读取。"""
import json
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from src.agent import run_tool_details
from src.passage import read_passage as read_dureader_passage

mcp = MCPServer("DuReader Agent", instructions="只读取 DuReader 公开语料；内容可能不可靠或过时。")


@mcp.tool()
def search_docs(query: str) -> list[dict]:
    """查询 DuReader，返回重排后的片段和段落 ID。"""
    if not query.strip():
        raise ToolError("查询不能为空")
    result, success = run_tool_details("search_docs", {"query": query})
    if not success:
        raise ToolError(result)
    return json.loads(result)


@mcp.tool()
def read_passage(passage_id: str) -> dict:
    """按 32 位小写十六进制段落 ID 读取 DuReader 正文。"""
    try:
        return read_dureader_passage(passage_id)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")

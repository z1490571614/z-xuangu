"""
调试MCP接口响应内容
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()


def debug_mcp_response():
    """调试MCP接口响应"""
    print("=" * 80)
    print("🔍 调试MCP接口响应内容")
    print("=" * 80)
    
    mcp_url = os.getenv("TDX_MCP_URL", "")
    mcp_api_key = os.getenv("TDX_MCP_API_KEY", "")
    
    # 测试查询
    test_query = "非ST非停牌非北交所股票，流通市值小于2000亿，昨日收盘价小于500元，近10日股价上涨，近100个交易日内涨停次数不少于3次"
    
    print(f"\n查询语句: {test_query}")
    print(f"条件数: 5个")
    
    # 步骤1: 创建会话
    print("\n📋 步骤1: 创建会话")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "tdx-api-key": mcp_api_key,
    }
    
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "xuangu-stock-selector",
                "version": "2.0.0"
            }
        },
        "id": 1
    }
    
    with httpx.Client(timeout=30.0) as client:
        response = client.post(mcp_url, json=payload, headers=headers)
        session_id = response.headers.get("mcp-session-id")
        print(f"  Session ID: {session_id}")
    
    # 步骤2: 执行查询
    print("\n📋 步骤2: 执行查询")
    headers["mcp-session-id"] = session_id
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "tdx_wenda_quotes",
            "arguments": {
                "question": test_query,
                "range": "AG",
                "size": "10",
                "page": "1"
            }
        },
        "id": 2
    }
    
    with httpx.Client(timeout=30.0) as client:
        response = client.post(mcp_url, json=payload, headers=headers)
        
        print(f"  状态码: {response.status_code}")
        print(f"  响应头: {dict(response.headers)}")
        
        response_text = response.text
        print(f"\n  响应内容长度: {len(response_text)} 字符")
        print(f"  响应内容前1000字符:")
        print(f"  {response_text[:1000]}")
        
        # 解析响应
        if response_text.startswith("event:"):
            lines = response_text.strip().split('\n')
            for line in lines:
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    rpc_result = json.loads(data_str)
                    
                    print(f"\n  JSON-RPC结果:")
                    print(f"  {json.dumps(rpc_result, indent=2, ensure_ascii=False)[:500]}")
                    
                    # 检查content
                    content = rpc_result.get("result", {}).get("content", [])
                    print(f"\n  Content数组长度: {len(content)}")
                    
                    if content:
                        text_content = content[0].get("text", "")
                        print(f"  Text内容长度: {len(text_content)} 字符")
                        print(f"  Text内容前500字符:")
                        print(f"  {text_content[:500]}")
                        
                        if text_content and text_content.strip():
                            try:
                                result = json.loads(text_content)
                                total = result.get("meta", {}).get("total", 0)
                                print(f"\n  ✅ 解析成功: 返回 {total} 条记录")
                            except json.JSONDecodeError as e:
                                print(f"\n  ❌ JSON解析失败: {e}")
                        else:
                            print(f"\n  ⚠️  Text内容为空")
        else:
            print(f"\n  响应不是SSE格式")


if __name__ == "__main__":
    debug_mcp_response()

import os

from backend.services.stock_selector import StockSelectorService
from backend.services.tdx_mcp_client import McpTemporaryUnavailable


def test_mcp_503_task_result_is_temporary_unavailable():
    from backend.services.tdx_selector import TdxSelectorService, create_default_task

    def fail_mcp(**kwargs):
        raise McpTemporaryUnavailable("MCP临时不可用: [EXECUTION_ERROR] API请求失败: 503 Service unavailable")

    result = TdxSelectorService()._execute_task(create_default_task(), fail_mcp)

    assert result["total_count"] == 0
    assert result["error_type"] == "mcp_temporary_unavailable"


def test_phase1_falls_back_when_mcp_task_has_error(monkeypatch):
    os.environ["ENABLE_LOCAL_FALLBACK"] = "true"
    service = StockSelectorService()

    monkeypatch.setattr(service.tdx_selector, "select", lambda tdx_mcp_func: {
        "stocks": [],
        "total_count": 0,
        "task_results": [{
            "error": "MCP临时不可用: 503 Service unavailable",
            "error_type": "mcp_temporary_unavailable",
        }],
    })

    class FakeLocalSelector:
        def select(self, **kwargs):
            return {"stocks": [], "total_count": 0, "source": "tdx_local"}

    import backend.services.tdx_local_selector as local_module
    monkeypatch.setattr(local_module, "TdxLocalSelectorService", lambda: FakeLocalSelector())

    phase = service._execute_phase1([], lambda **kwargs: None, "20260507")

    assert phase.success is True
    assert phase.source == "tdx_local"

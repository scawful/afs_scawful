"""Tests for MCP tool definitions and handlers."""

from __future__ import annotations

from unittest.mock import patch

from afs_scawful.mcp_tools import register_mcp_tools


def test_register_mcp_tools_returns_list():
    tools = register_mcp_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_all_tools_have_required_keys():
    tools = register_mcp_tools()
    for tool in tools:
        assert "name" in tool, f"Tool missing name: {tool}"
        assert "description" in tool, f"Tool {tool.get('name')} missing description"
        assert "inputSchema" in tool, f"Tool {tool['name']} missing inputSchema"
        assert "handler" in tool, f"Tool {tool['name']} missing handler"
        assert callable(tool["handler"]), f"Tool {tool['name']} handler not callable"


def test_all_tools_have_valid_schemas():
    tools = register_mcp_tools()
    for tool in tools:
        schema = tool["inputSchema"]
        assert isinstance(schema, dict), f"Tool {tool['name']} schema not a dict"
        assert schema.get("type") == "object", f"Tool {tool['name']} schema type != object"


def test_tool_names_are_unique():
    tools = register_mcp_tools()
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


def test_handle_training_paths():
    from afs_scawful.mcp_tools import _handle_training_paths

    result = _handle_training_paths({})
    assert "training_root" in result
    assert "datasets_root" in result
    assert "index_root" in result


def test_handle_infra_config():
    from afs_scawful.mcp_tools import _handle_infra_config

    result = _handle_infra_config({})
    assert "vultr" in result
    assert "monitoring" in result
    assert "training" in result
    assert "backup" in result


def test_handle_vast_instances():
    from afs_scawful.mcp_tools import _handle_vast_instances

    result = _handle_vast_instances({})
    assert "instances" in result
    assert isinstance(result["instances"], list)


def test_handle_models_list():
    from afs_scawful.mcp_tools import _handle_models_list

    result = _handle_models_list({})
    assert "models" in result
    models = result["models"]
    assert "nayru" in models
    assert "veran" in models
    assert "farore" in models
    assert "majora" not in models
    for name, info in models.items():
        assert "ollama_tag" in info
        assert "description" in info
        assert "domains" in info


def test_handle_assemble_no_code():
    from afs_scawful.mcp_tools import _handle_assemble

    result = _handle_assemble({})
    assert "error" in result


def test_handle_assemble_missing_asar():
    from afs_scawful.mcp_tools import _handle_assemble

    result = _handle_assemble({
        "code": "LDA #$00",
        "asar_path": "/nonexistent/asar",
    })
    assert "error" in result


def test_handle_alert_send_no_message():
    from afs_scawful.mcp_tools import _handle_alert_send

    result = _handle_alert_send({})
    assert "error" in result


def test_handle_alert_send_mock():
    from afs_scawful.mcp_tools import _handle_alert_send

    with patch("afs_scawful.alerting.AlertDispatcher") as mock_cls:
        mock_dispatcher = mock_cls.return_value
        mock_dispatcher.send.return_value = True
        result = _handle_alert_send({"message": "test alert", "level": "info"})
    assert "sent" in result


def test_handle_training_status_error():
    from afs_scawful.mcp_tools import _handle_training_status

    with patch("afs_scawful.dashboard.Dashboard", side_effect=RuntimeError("no tracker")):
        result = _handle_training_status({})
    assert "error" in result


def test_expected_tool_names():
    tools = register_mcp_tools()
    names = {t["name"] for t in tools}
    expected = {
        "training.status",
        "training.paths",
        "infra.config",
        "vast.status",
        "vast.instances",
        "assembly.compile",
        "alert.send",
        "models.experts",
        "resource.index",
    }
    assert expected == names

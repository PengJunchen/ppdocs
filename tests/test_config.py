from __future__ import annotations

import json
import os
import tempfile

import pytest

from doc_parser.config import _set_nested, get_config, get_section, load_config


class TestConfigLoad:
    def test_load_default_config(self):
        cfg = load_config()
        assert "server" in cfg
        assert "pipeline" in cfg
        assert "llm" in cfg
        assert "embedding" in cfg
        assert "orchestrator" in cfg
        assert "storage" in cfg

    def test_load_custom_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"server": {"host": "127.0.0.1", "port": 9000}, "llm": {"model": "test-model"}}, f)
            f.flush()
            cfg = load_config(f.name)
            assert cfg["server"]["host"] == "127.0.0.1"
            assert cfg["server"]["port"] == 9000
            assert cfg["llm"]["model"] == "test-model"
        os.unlink(f.name)

    def test_load_missing_config(self):
        cfg = load_config("/nonexistent/config.json")
        assert isinstance(cfg, dict)

    def test_get_config_returns_loaded(self):
        load_config()
        cfg = get_config()
        assert "server" in cfg

    def test_get_section(self):
        load_config()
        server = get_section("server")
        assert "host" in server
        assert "port" in server

    def test_get_section_default(self):
        result = get_section("nonexistent", {"default": True})
        assert result == {"default": True}


class TestEnvOverrides:
    def test_env_override_string(self):
        os.environ["DOCPARSER_MINERU_URL"] = "http://test:9999"
        try:
            cfg = load_config()
            assert cfg["pipeline"]["mineru_url"] == "http://test:9999"
        finally:
            del os.environ["DOCPARSER_MINERU_URL"]

    def test_env_override_int(self):
        os.environ["DOCPARSER_MAX_TASKS"] = "500"
        try:
            cfg = load_config()
            assert cfg["task_manager"]["max_tasks"] == 500
        finally:
            del os.environ["DOCPARSER_MAX_TASKS"]


class TestSetNested:
    def test_simple_key(self):
        d = {"a": "old"}
        _set_nested(d, "a", "new")
        assert d["a"] == "new"

    def test_nested_key(self):
        d = {"x": {"y": "old"}}
        _set_nested(d, "x.y", "hello")
        assert d["x"]["y"] == "hello"

    def test_create_intermediate(self):
        d = {}
        _set_nested(d, "a.b.c", "val")
        assert d["a"]["b"]["c"] == "val"

    def test_int_type_preserved(self):
        d = {"count": 10}
        _set_nested(d, "count", "20")
        assert d["count"] == 20

    def test_bool_type_preserved(self):
        d = {"flag": True}
        _set_nested(d, "flag", "true")
        assert d["flag"] is True
        _set_nested(d, "flag", "false")
        assert d["flag"] is False

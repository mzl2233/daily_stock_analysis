# -*- coding: utf-8 -*-
"""Tests for env-based LLM channel parsing."""

import os
import unittest
from unittest.mock import patch

from src.config import (
    Config,
    get_effective_agent_models_to_try,
    get_effective_agent_primary_model,
)


class LLMChannelConfigTestCase(unittest.TestCase):
    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_protocol_prefixes_bare_model_names(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "deepseek",
            "LLM_PRIMARY_BASE_URL": "https://api.deepseek.com/v1",
            "LLM_PRIMARY_API_KEY": "sk-test-value",
            "LLM_PRIMARY_MODELS": "deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["protocol"], "deepseek")
        self.assertEqual(config.llm_channels[0]["models"], ["deepseek/deepseek-chat"])
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["model"], "deepseek/deepseek-chat")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_openai_compatible_channel_prefixes_non_provider_slash_models(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "siliconflow",
            "LLM_SILICONFLOW_PROTOCOL": "openai",
            "LLM_SILICONFLOW_BASE_URL": "https://api.siliconflow.cn/v1",
            "LLM_SILICONFLOW_API_KEY": "sk-test-value",
            "LLM_SILICONFLOW_MODELS": "Qwen/Qwen3-8B,deepseek-ai/DeepSeek-V3",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(
            config.llm_channels[0]["models"],
            ["openai/Qwen/Qwen3-8B", "openai/deepseek-ai/DeepSeek-V3"],
        )

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_alias_prefixed_models_are_canonicalized_once(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "vertex",
            "LLM_VERTEX_PROTOCOL": "vertex_ai",
            "LLM_VERTEX_API_KEY": "sk-test-value",
            "LLM_VERTEX_MODELS": "vertexai/gemini-2.5-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels[0]["models"], ["vertex_ai/gemini-2.5-flash"])
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["model"], "vertex_ai/gemini-2.5-flash")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_minimax_prefixed_models_are_not_rewritten_for_openai_compatible_channels(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_BASE_URL": "https://api.example.com/v1",
            "LLM_PRIMARY_API_KEY": "sk-test-value",
            "LLM_PRIMARY_MODELS": "minimax/MiniMax-M1",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels[0]["models"], ["minimax/MiniMax-M1"])
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["model"], "minimax/MiniMax-M1")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_disabled_channel_is_skipped(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_ENABLED": "false",
            "LLM_PRIMARY_API_KEY": "sk-test-value",
            "LLM_PRIMARY_MODELS": "gpt-4o-mini",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels, [])
        self.assertEqual(config.llm_model_list, [])

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_local_ollama_channel_can_skip_api_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "local",
            "LLM_LOCAL_PROTOCOL": "ollama",
            "LLM_LOCAL_BASE_URL": "http://127.0.0.1:11434",
            "LLM_LOCAL_API_KEY": "",
            "LLM_LOCAL_MODELS": "llama3.2",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        params = config.llm_model_list[0]["litellm_params"]
        self.assertEqual(params["model"], "ollama/llama3.2")
        self.assertNotIn("api_key", params)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_channel_specific_api_key_takes_precedence_over_legacy_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "deepseek",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "LLM_DEEPSEEK_API_KEY": "sk-channel-key",
            "LLM_DEEPSEEK_MODELS": "deepseek-chat",
            "DEEPSEEK_API_KEY": "sk-legacy-key",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-channel-key"])
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["api_key"], "sk-channel-key")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_deepseek_channel_falls_back_to_legacy_deepseek_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "deepseek",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "LLM_DEEPSEEK_MODELS": "deepseek-chat,deepseek-reasoner",
            "DEEPSEEK_API_KEY": "sk-deepseek-legacy",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-deepseek-legacy"])
        self.assertEqual(
            config.llm_channels[0]["models"],
            ["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"],
        )

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_aihubmix_channel_falls_back_to_legacy_aihubmix_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "aihubmix",
            "LLM_AIHUBMIX_BASE_URL": "https://api.aihubmix.com/v1",
            "LLM_AIHUBMIX_MODELS": "gpt-4o-mini",
            "AIHUBMIX_KEY": "sk-aihubmix-legacy",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-aihubmix-legacy"])
        params = config.llm_model_list[0]["litellm_params"]
        self.assertEqual(params["api_key"], "sk-aihubmix-legacy")
        self.assertEqual(params["extra_headers"]["APP-Code"], "GPIJ3886")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_openai_channel_falls_back_to_legacy_openai_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "openai",
            "LLM_OPENAI_BASE_URL": "https://api.openai.com/v1",
            "LLM_OPENAI_MODELS": "gpt-4o-mini",
            "OPENAI_API_KEY": "sk-openai-legacy",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-openai-legacy"])
        self.assertEqual(config.llm_channels[0]["models"], ["openai/gpt-4o-mini"])

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_gemini_channel_falls_back_to_legacy_gemini_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "gemini",
            "LLM_GEMINI_MODELS": "gemini-2.5-flash",
            "GEMINI_API_KEY": "sk-gemini-legacy",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-gemini-legacy"])
        self.assertEqual(config.llm_channels[0]["models"], ["gemini/gemini-2.5-flash"])

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_anthropic_channel_falls_back_to_legacy_anthropic_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "claude",
            "LLM_CLAUDE_MODELS": "claude-3-5-sonnet",
            "ANTHROPIC_API_KEY": "sk-anthropic-legacy",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_models_source, "llm_channels")
        self.assertEqual(config.llm_channels[0]["protocol"], "anthropic")
        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-anthropic-legacy"])
        self.assertEqual(config.llm_channels[0]["models"], ["anthropic/claude-3-5-sonnet"])

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_aihubmix_prefers_aihubmix_key_over_openai_keys(self, _mock_parse_yaml, _mock_setup_env) -> None:
        """When both AIHUBMIX_KEY and OPENAI_API_KEYS exist, AIHUBMIX_KEY wins."""
        env = {
            "LLM_CHANNELS": "aihubmix",
            "LLM_AIHUBMIX_BASE_URL": "https://api.aihubmix.com/v1",
            "LLM_AIHUBMIX_MODELS": "gpt-4o-mini",
            "AIHUBMIX_KEY": "sk-aihubmix-correct",
            "OPENAI_API_KEYS": "sk-openai-wrong-1,sk-openai-wrong-2",
            "OPENAI_API_KEY": "sk-openai-wrong-single",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels[0]["api_keys"], ["sk-aihubmix-correct"])
        self.assertEqual(config.llm_model_list[0]["litellm_params"]["api_key"], "sk-aihubmix-correct")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_spoofed_host_does_not_trigger_legacy_key_fallback(self, _mock_parse_yaml, _mock_setup_env) -> None:
        """Attacker-controlled domains like api.openai.com.evil.tld must not receive legacy keys."""
        env = {
            "LLM_CHANNELS": "evil",
            "LLM_EVIL_PROTOCOL": "openai",
            "LLM_EVIL_BASE_URL": "https://api.openai.com.evil.tld/v1",
            "LLM_EVIL_MODELS": "gpt-4o-mini",
            "OPENAI_API_KEY": "sk-openai-secret",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        # Channel should be skipped (no key resolved), falling back to legacy_env
        self.assertEqual(config.llm_channels, [])
        self.assertEqual(config.llm_models_source, "legacy_env")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_provider_named_channel_with_spoofed_base_url_blocks_legacy_key(self, _mock_parse_yaml, _mock_setup_env) -> None:
        """LLM_CHANNELS=openai with a non-openai base_url must NOT receive OPENAI_API_KEY."""
        env = {
            "LLM_CHANNELS": "openai",
            "LLM_OPENAI_BASE_URL": "https://api.openai.com.evil.tld/v1",
            "LLM_OPENAI_MODELS": "gpt-4o-mini",
            "OPENAI_API_KEY": "sk-openai-secret",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels, [])
        self.assertEqual(config.llm_models_source, "legacy_env")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_custom_openai_compatible_channel_does_not_fall_back_to_legacy_keys(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "my_proxy",
            "LLM_MY_PROXY_PROTOCOL": "openai",
            "LLM_MY_PROXY_BASE_URL": "https://proxy.example.com/v1",
            "LLM_MY_PROXY_MODELS": "gpt-4o-mini",
            "OPENAI_API_KEY": "sk-openai-legacy",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.llm_channels, [])
        self.assertEqual(config.llm_models_source, "legacy_env")
        self.assertEqual(config.llm_model_list[0]["model_name"], "__legacy_openai__")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_falls_back_to_legacy_provider_temperature(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "GEMINI_API_KEY": "secret-key-value",
            "GEMINI_TEMPERATURE": "0.15",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.litellm_model, "gemini/gemini-3-flash-preview")
        self.assertAlmostEqual(config.llm_temperature, 0.15)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_prefers_unified_setting_when_present(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "GEMINI_API_KEY": "secret-key-value",
            "GEMINI_TEMPERATURE": "0.15",
            "LLM_TEMPERATURE": "0.35",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertAlmostEqual(config.llm_temperature, 0.35)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_falls_back_to_openai_temperature(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_API_KEY": "sk-test",
            "LLM_PRIMARY_MODELS": "gpt-4o",
            "LITELLM_MODEL": "openai/gpt-4o",
            "OPENAI_TEMPERATURE": "0.42",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertAlmostEqual(config.llm_temperature, 0.42)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_falls_back_to_any_legacy_when_provider_mismatch(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LLM_CHANNELS": "primary",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_API_KEY": "sk-test",
            "LLM_PRIMARY_MODELS": "gpt-4o",
            "LITELLM_MODEL": "openai/gpt-4o",
            "ANTHROPIC_TEMPERATURE": "0.55",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertAlmostEqual(config.llm_temperature, 0.55)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_llm_temperature_ignores_invalid_value(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "GEMINI_API_KEY": "secret-key-value",
            "LLM_TEMPERATURE": "high",
            "GEMINI_TEMPERATURE": "0.25",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertAlmostEqual(config.llm_temperature, 0.25)

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_local_openai_compatible_channel_defaults_to_openai_protocol(self, _mock_parse_yaml, _mock_setup_env) -> None:
        """Localhost channels without explicit protocol should default to openai, not ollama."""
        env = {
            "LLM_CHANNELS": "local",
            "LLM_LOCAL_BASE_URL": "http://127.0.0.1:8000/v1",
            "LLM_LOCAL_API_KEY": "not-needed",
            "LLM_LOCAL_MODELS": "my-model",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        params = config.llm_model_list[0]["litellm_params"]
        self.assertEqual(params["model"], "openai/my-model")
        self.assertEqual(config.llm_channels[0]["protocol"], "openai")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_model_empty_inherits_primary_model(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test-value",
            "OPENAI_MODEL": "gpt-4o-mini",
            "AGENT_LITELLM_MODEL": "",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_litellm_model, "")
        self.assertEqual(get_effective_agent_primary_model(config), "openai/gpt-4o-mini")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_model_without_provider_prefix_is_normalized(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test-value",
            "OPENAI_MODEL": "gpt-4o-mini",
            "AGENT_LITELLM_MODEL": "deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_litellm_model, "openai/deepseek-chat")
        self.assertEqual(get_effective_agent_primary_model(config), "openai/deepseek-chat")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_models_to_try_are_deduped_in_order(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test-value",
            "LITELLM_MODEL": "gemini/gemini-2.5-flash",
            "AGENT_LITELLM_MODEL": "openai/gpt-4o-mini",
            "LITELLM_FALLBACK_MODELS": "openai/gpt-4o-mini,openai/gpt-4o-mini,gemini/gemini-2.5-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(
            get_effective_agent_models_to_try(config),
            ["openai/gpt-4o-mini", "gemini/gemini-2.5-flash"],
        )

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_agent_models_to_try_dedupes_semantically_equivalent_openai_models(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test-value",
            "LITELLM_MODEL": "gemini/gemini-2.5-flash",
            "AGENT_LITELLM_MODEL": "gpt-4o-mini",
            "LITELLM_FALLBACK_MODELS": "openai/gpt-4o-mini,gpt-4o-mini",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(
            get_effective_agent_models_to_try(config),
            ["openai/gpt-4o-mini"],
        )

    @patch("src.config.setup_env")
    @patch.object(
        Config,
        "_parse_litellm_yaml",
        return_value=[
            {
                "model_name": "gpt4o",
                "litellm_params": {
                    "model": "openai/gpt-4o-mini",
                    "api_key": "sk-test-value",
                },
            }
        ],
    )
    def test_agent_model_preserves_yaml_alias_without_provider_prefix(self, _mock_parse_yaml, _mock_setup_env) -> None:
        env = {
            "LITELLM_CONFIG": "/tmp/litellm.yaml",
            "AGENT_LITELLM_MODEL": "gpt4o",
            "LITELLM_FALLBACK_MODELS": "openai/gpt-4o-mini",
        }

        with patch.dict(os.environ, env, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_litellm_model, "gpt4o")
        self.assertEqual(get_effective_agent_primary_model(config), "gpt4o")
        self.assertEqual(
            get_effective_agent_models_to_try(config),
            ["gpt4o", "openai/gpt-4o-mini"],
        )


if __name__ == "__main__":
    unittest.main()

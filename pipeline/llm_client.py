"""LLM provider 추상화. 단일 함수 generate_section만 expose.

지원 백엔드:
- claude_code (default): 로컬 Claude Code CLI 호출 — 구독 인증 사용, API 키 불필요
- anthropic: Anthropic SDK 직접 호출 — ANTHROPIC_API_KEY 필요 (별도 과금)

초기 6개월 동안 두 백엔드 중 하나로 *고정*해서 운영하고, 혼합은 validator·품질 베이스라인이 안정된 후 별도 브랜치에서 도입.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pipeline import config


class _ClaudeCodeBackend:
    """`claude -p` CLI를 subprocess로 호출. 구독 인증을 그대로 사용."""

    def __init__(self) -> None:
        self._bin = config.CLAUDE_CODE_BIN
        self._model = config.CLAUDE_CODE_MODEL
        self._timeout = config.CLAUDE_CODE_TIMEOUT_SEC
        self._cwd = config.CLAUDE_CODE_NEUTRAL_CWD

    def generate(self, system: str, user: str, max_tokens: int) -> str:
        # 임시 파일은 user-only readable (0o600). NamedTemporaryFile 기본도 600이지만 명시.
        import os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(system)
            sys_path = Path(f.name)
        try:
            os.chmod(sys_path, 0o600)
        except OSError:
            pass

        try:
            args = [
                self._bin,
                "-p",
                "--system-prompt-file", str(sys_path),
                "--model", self._model,
                "--tools", "",
                "--disable-slash-commands",
                "--no-session-persistence",
                "--output-format", "text",
                "--exclude-dynamic-system-prompt-sections",
                "--permission-mode", "default",
            ]
            try:
                result = subprocess.run(
                    args,
                    input=user,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    cwd=self._cwd,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(
                    f"claude CLI timeout ({self._timeout}s): {e}"
                ) from e

            if result.returncode != 0:
                raise RuntimeError(
                    f"claude CLI failed (rc={result.returncode}): "
                    f"stderr={result.stderr[:1000]}"
                )
            return result.stdout
        finally:
            sys_path.unlink(missing_ok=True)


class _AnthropicBackend:
    def __init__(self) -> None:
        from anthropic import Anthropic
        self._client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._model = config.ANTHROPIC_MODEL

    def generate(self, system: str, user: str, max_tokens: int) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts)


_backend = None


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    if config.LLM_PROVIDER not in config.ALLOWED_PROVIDERS_PHASE1:
        raise RuntimeError(
            f"phase 1: provider '{config.LLM_PROVIDER}' 비허용. "
            f"허용: {config.ALLOWED_PROVIDERS_PHASE1}. "
            "provider 교체는 validator·품질 안정 후."
        )
    if config.LLM_PROVIDER == "claude_code":
        _backend = _ClaudeCodeBackend()
    elif config.LLM_PROVIDER == "anthropic":
        _backend = _AnthropicBackend()
    else:
        raise RuntimeError(f"unknown provider: {config.LLM_PROVIDER}")
    return _backend


def reset_backend() -> None:
    """테스트 용도: 백엔드 캐시 리셋."""
    global _backend
    _backend = None


def generate_section(
    system_prompt: str, user_prompt: str, max_tokens: int = 8192
) -> str:
    return _get_backend().generate(system_prompt, user_prompt, max_tokens)

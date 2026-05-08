"""환경변수·경로 설정. 모든 모듈의 single source of truth."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)

FRAME_PATH = REPO_ROOT / "_frame.md"
PERSONA_PATH = REPO_ROOT / "_persona.md"
WATCHLIST_PATH = REPO_ROOT / "_watchlist.md"
COMPANIES_DIR = REPO_ROOT / "companies"
INDUSTRY_NOTES_DIR = REPO_ROOT / "industry_notes"
INDEX_PATH = REPO_ROOT / "_index.md"
GLOSSARY_PATH = REPO_ROOT / "_glossary.md"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude_code")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

CLAUDE_CODE_BIN = os.getenv("CLAUDE_CODE_BIN", "claude")
CLAUDE_CODE_MODEL = os.getenv("CLAUDE_CODE_MODEL", "sonnet")
CLAUDE_CODE_TIMEOUT_SEC = int(os.getenv("CLAUDE_CODE_TIMEOUT_SEC", "1800"))
# 사용자 글로벌 규칙: /tmp 직접 사용 금지 → /home/soccz/22tb/tmp 사용.
# claude CLI subprocess의 작업 디렉토리. 환경변수 없으면 22tb 하위로 폴백.
_DEFAULT_NEUTRAL_CWD = "/home/soccz/22tb/tmp"
if not Path(_DEFAULT_NEUTRAL_CWD).exists():
    _DEFAULT_NEUTRAL_CWD = "/tmp"  # 22tb 하위 미존재 환경 폴백
CLAUDE_CODE_NEUTRAL_CWD = os.getenv("CLAUDE_CODE_NEUTRAL_CWD", _DEFAULT_NEUTRAL_CWD)

DART_API_KEY = os.getenv("DART_API_KEY")
DART_BASE_URL = "https://opendart.fss.or.kr/api"

VALIDATOR_MAX_RETRIES = int(os.getenv("VALIDATOR_MAX_RETRIES", "3"))

ALLOWED_PROVIDERS_PHASE1 = {"anthropic", "claude_code"}

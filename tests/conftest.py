"""Make the agent package importable in tests without installing it.

Adds <repo>/agent to sys.path so `from app...` resolves.
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

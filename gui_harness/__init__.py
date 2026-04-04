"""
gui_harness — GUI automation powered by Agentic Programming.

Core exports:
    GUIRuntime          GUI-optimized LLM runtime (extends AnthropicRuntime)
    observe             Observe the current screen state
    act                 Perform a GUI action
    verify              Verify action results
    learn               Learn an app's UI
    navigate            Navigate via state graph
    remember            Manage visual memory
    send_message        High-level: send a message
    read_messages       High-level: read messages
"""

from gui_harness.runtime import GUIRuntime
from gui_harness.functions import observe, act, verify, learn, navigate, remember
from gui_harness.tasks import execute_task, send_message, read_messages

__all__ = [
    "GUIRuntime",
    "execute_task",
    "observe",
    "act",
    "verify",
    "learn",
    "navigate",
    "remember",
    "send_message",
    "read_messages",
]

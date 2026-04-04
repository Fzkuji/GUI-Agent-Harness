"""
gui_harness.tasks — high-level composite tasks built from @agentic_functions.
"""

from gui_harness.tasks.execute_task import execute_task
from gui_harness.tasks.send_message import send_message
from gui_harness.tasks.read_messages import read_messages

__all__ = ["execute_task", "send_message", "read_messages"]

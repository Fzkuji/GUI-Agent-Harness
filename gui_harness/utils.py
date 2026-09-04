"""
gui_harness.utils — shared utilities.

Delegates JSON parsing to openprogram.programs.workflow.json_parsing
(single implementation, maintained in the OpenProgram project).
"""

from openprogram.programs.workflow.json_parsing import parse_json  # noqa: F401

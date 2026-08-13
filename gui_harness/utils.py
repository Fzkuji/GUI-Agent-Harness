"""
gui_harness.utils — shared utilities.

Delegates JSON parsing to openprogram.programs.agentic_functions.json_parsing
(single implementation, maintained in the OpenProgram project).
"""

try:  # openprogram 重构后 parse_json 迁到 _utils;保留旧路径兼容
    from openprogram.programs.agentic_functions._utils import parse_json  # noqa: F401
except ImportError:  # pragma: no cover
    from openprogram.programs.agentic_functions.json_parsing import parse_json  # noqa: F401

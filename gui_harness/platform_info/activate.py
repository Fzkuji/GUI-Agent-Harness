#!/usr/bin/env python3
"""
GUI Agent Skill activation script.
Run at skill load time to detect platform and output relevant context.

Usage:
    python3 activate.py              # Detect local platform
    python3 activate.py --remote     # Also detect remote target (if configured)

Output is formatted for direct injection into model context.
"""

import os
import sys
import shutil
import argparse

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from platforms.detect import detect_platform


def activate(remote_info=None):
    """Output platform context for model consumption."""
    
    info = detect_platform()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    print("# GUI Agent — Platform Context")
    print()
    print(f"**Host Platform:** {info['os_name']} ({info['machine']})")
    print(f"**Display Server:** {info['display_server']}")
    print(f"**Available Tools:** {', '.join(sorted(info['tools'].keys()))}")
    print()
    
    if info.get('recommended_input'):
        print(f"**Recommended Input:** {info['recommended_input']}")
    if info.get('recommended_screenshot'):
        print(f"**Recommended Screenshot:** {info['recommended_screenshot']}")
    if info.get('recommended_clipboard'):
        print(f"**Recommended Clipboard:** {info['recommended_clipboard']}")
    if info.get('recommended_ocr'):
        print(f"**Recommended OCR:** {info['recommended_ocr']}")
    print()
    
    # Load platform guide
    guide_path = os.path.join(base_dir, "platforms", f"{info['platform_guide']}.md")
    if os.path.exists(guide_path):
        print(f"## Platform Guide ({info['platform_guide']})")
        print()
        print(open(guide_path).read())
    else:
        print(f"⚠️ No platform guide found for: {info['platform_guide']}")
    
    # Copy platform-specific actions to _actions.yaml
    platform_map = {"Darwin": "macos", "Linux": "linux"}
    platform_key = platform_map.get(info['os'], info['os'].lower())
    actions_src = os.path.join(base_dir, "actions", f"_actions_{platform_key}.yaml")
    actions_dst = os.path.join(base_dir, "actions", "_actions.yaml")
    if os.path.exists(actions_src):
        shutil.copy2(actions_src, actions_dst)
        print(f"\n✅ Actions: _actions_{platform_key}.yaml → _actions.yaml")
    
    # Remote target info (if provided)
    if remote_info:
        print()
        print("---")
        print()
        print("## Remote Target Platform")
        print()
        print(f"**Target:** {remote_info.get('os_name', '?')} ({remote_info.get('machine', '?')})")
        print(f"**Available Tools:** {', '.join(sorted(remote_info.get('tools', {}).keys()))}")
        
        remote_guide = remote_info.get('platform_guide', '')
        remote_guide_path = os.path.join(base_dir, "platforms", f"{remote_guide}.md")
        if os.path.exists(remote_guide_path):
            print()
            print(f"### Remote Platform Guide ({remote_guide})")
            print()
            print(open(remote_guide_path).read())
        
        print()
        print("### Dual-Platform Operation")
        print("- **OCR & Detection:** Run on HOST (has Vision framework / better GPU)")
        print("- **GUI Actions:** Execute on TARGET (where the apps are running)")
        print("- **Screenshots:** Capture from TARGET, transfer to HOST for analysis")
        print("- **Coordinates:** No scaling needed if target is non-Retina (1:1 pixels)")


def main():
    parser = argparse.ArgumentParser(description="GUI Agent Platform Activation")
    parser.add_argument("--remote", action="store_true", help="Also detect remote target")
    parser.add_argument("--remote-cmd", type=str, help="Command to run detect.py on remote (e.g., 'ssh user@host python3')")
    args = parser.parse_args()
    
    remote_info = None
    if args.remote and args.remote_cmd:
        import subprocess
        try:
            result = subprocess.run(
                args.remote_cmd.split() + [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "platforms", "detect.py"), "--json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                import json
                remote_info = json.loads(result.stdout)
        except Exception as e:
            print(f"⚠️ Remote detection failed: {e}", file=sys.stderr)
    
    activate(remote_info)


if __name__ == "__main__":
    main()

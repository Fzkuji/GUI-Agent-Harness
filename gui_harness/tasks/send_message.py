"""
gui_harness.tasks.send_message — send a message in a messaging app.

High-level task: observe → navigate → type → send → verify.
compress=True hides sub-steps from summarize().
"""

from __future__ import annotations

from openprogram import agentic_function


@agentic_function()
def send_message(app_name: str, recipient: str, message: str,
                 runtime=None) -> dict:
    """Send a message to a recipient in a messaging app.

    Steps:
      1. observe — find current state
      2. navigate — go to conversation with recipient
      3. act("type") — type the message
      4. act("click") — click send / press Enter
      5. verify — confirm message was sent

    compress=True: callers see only the final result.

    Args:
        app_name:  Messaging app (e.g., "WeChat", "Discord", "Telegram").
        recipient: Name of the recipient/contact.
        message:   Message text to send.
        runtime:   Runtime instance (required).

    Returns:
        dict with keys: app_name, recipient, message, success, evidence
    """
    from gui_harness.planning.observe import observe
    from gui_harness.planning.act import act
    from gui_harness.planning.navigate import navigate
    from gui_harness.planning.verify import verify

    if runtime is None:
        raise ValueError("send_message() requires a runtime argument")
    rt = runtime

    # 1. Observe
    obs = observe(task=f"Find conversation with {recipient} in {app_name}",
                  app_name=app_name)

    # 2. Navigate if needed
    if not obs.get("target_visible"):
        navigate(target_state=f"conversation_{recipient}",
                 app_name=app_name, runtime=rt)

    # 3. Click input + type
    act(action="click", target="message input field",
        app_name=app_name, runtime=rt)
    act(action="type", target="message input field",
        text=message, app_name=app_name, runtime=rt)

    # 4. Send
    act(action="click", target="send button",
        app_name=app_name, runtime=rt)

    # 5. Verify
    result = verify(
        expected=f'Message "{message[:30]}..." appears in the conversation',
    )

    return {
        "app_name": app_name,
        "recipient": recipient,
        "message": message,
        "success": result.get("verified", False),
        "evidence": result.get("evidence", ""),
    }

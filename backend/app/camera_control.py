"""Agent-side control of the inspector's device camera.

The camera lives in the inspector's BROWSER (getUserMedia), not on this
server. This tool doesn't touch hardware: the frontend watches for its tool
calls and starts/stops the browser camera (or captures a frame) accordingly.
The confirmation string tells the model what to expect next.
"""

from strands import tool

# rear/front are explicit facing picks; flip toggles whatever is current.
_ACTIONS = ("start", "stop", "snap", "flip", "rear", "front")


@tool
def control_camera(action: str) -> str:
    """Control the inspector's device camera (the one in their browser).

    Use this yourself whenever you need to see — you do not need to ask the
    inspector to press anything (their browser may still ask them to grant
    camera permission the first time). Works on any device: laptop/desktop
    webcams, and the front and rear lenses on phones and tablets.

    Camera facing:
        The camera defaults to the REAR / outward-facing lens ("environment"),
        which is what you want for inspecting the property — photos and videos
        should frame the home, not the inspector. Only switch to the front
        (selfie) camera if the inspector explicitly wants to appear on camera
        or asks for it.

    Args:
        action: One of —
            "start"  turn the camera on and begin receiving live frames
                     (uses the rear/outward lens by default),
            "stop"   turn the camera off,
            "snap"   capture one full-quality frame right now (camera must
                     already be on),
            "flip"   toggle between the front and rear cameras,
            "rear"   explicitly select the rear / outward-facing (non-selfie)
                     camera — the default and preferred view for inspections,
            "front"  explicitly select the front / selfie camera.

    Returns:
        str: What will happen next.
    """
    normalized = action.strip().lower()
    if normalized not in _ACTIONS:
        return (
            f"Unknown action {action!r} — use start, stop, snap, flip, rear, or front."
        )
    if normalized == "start":
        return (
            "Camera start requested (rear/outward-facing lens by default). Live "
            "frames will begin arriving as image input within a couple of seconds "
            "(the inspector may need to grant browser camera permission first)."
        )
    if normalized == "snap":
        return "Snap requested — a full-quality frame is being captured and sent now."
    if normalized == "flip":
        return "Camera flip requested — switching between front and rear cameras; frames continue."
    if normalized == "rear":
        return (
            "Rear/outward-facing camera requested — the preferred non-selfie view "
            "for framing the property; frames continue."
        )
    if normalized == "front":
        return "Front/selfie camera requested — switching to the inspector-facing lens; frames continue."
    return "Camera stop requested — frames will cease."

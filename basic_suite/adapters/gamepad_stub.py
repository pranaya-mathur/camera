class GamepadBridge:
    """Gamepad stub for robotics-control style API wiring."""

    def map_input(self, axes: dict, buttons: dict) -> dict:
        # Placeholder mapping logic to demonstrate endpoint contract.
        return {
            "throttle": float(axes.get("ly", 0.0)) * -1.0,
            "yaw": float(axes.get("lx", 0.0)),
            "camera_pan": float(axes.get("rx", 0.0)),
            "camera_tilt": float(axes.get("ry", 0.0)),
            "triggered": [k for k, v in buttons.items() if bool(v)],
        }

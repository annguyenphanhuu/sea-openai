"""Shared thresholds and pure compensation arithmetic."""

tick_min = 30
p_contact = 0.7
p_watch = 0.2
guard_heartbeat_max_min = 60
max_turns = 8


def late_xu_for(order_value_vnd: int) -> int:
    """Quote 5%, floored to thousands and clamped; do not decide eligibility."""
    if isinstance(order_value_vnd, bool) or not isinstance(order_value_vnd, int):
        raise TypeError("order_value_vnd must be an integer")
    if order_value_vnd < 0:
        raise ValueError("order_value_vnd must be non-negative")
    rounded_xu = (order_value_vnd * 5 // 100_000) * 1_000
    return min(1_000_000, max(10_000, rounded_xu))

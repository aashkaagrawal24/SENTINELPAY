from datetime import UTC, datetime


def active_policy(
    policies: list[dict], product_id: str, category: str, at: datetime | None = None
) -> dict | None:
    """Deterministically select most-specific current policy; never mutate history."""
    now = at or datetime.now(UTC)
    candidates = [
        p
        for p in policies
        if p["status"] == "ACTIVE"
        and p["valid_from"] <= now
        and (p.get("valid_until") is None or p["valid_until"] > now)
        and (
            p["scope"] == "GLOBAL"
            or (p["scope"] == "PRODUCT" and p.get("scope_reference") == product_id)
            or (p["scope"] == "CATEGORY" and p.get("scope_reference") == category)
        )
    ]
    rank = {"GLOBAL": 0, "CATEGORY": 1, "PRODUCT": 2}
    return max(candidates, key=lambda p: (rank[p["scope"]], p["version"])) if candidates else None

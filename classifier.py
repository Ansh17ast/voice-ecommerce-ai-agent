def classify_lead(lead):
    """
    Classify a lead as HOT, WARM, or COLD.
    """

    budget = lead.get("budget")
    timeline = lead.get("timeline")
    barrier = lead.get("barrier")
    features = lead.get("features", [])

    # WARM:
    # The customer is interested but has a clear barrier.
    # Check this BEFORE HOT.
    if barrier:
        return {
            "classification": "WARM",
            "reason": f"Customer is interested but has a barrier: {barrier}"
        }

    # HOT:
    # Strong buying signals with no blocking barrier.
    if budget and timeline and len(features) > 0:
        return {
            "classification": "HOT",
            "reason": "Customer has a stated budget, timeline, and specific requirements."
        }

    # COLD:
    # Not enough strong buying signals.
    return {
        "classification": "COLD",
        "reason": "Customer has not provided enough strong buying signals."
    }
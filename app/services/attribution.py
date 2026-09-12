from uuid import UUID


def classify_attribution(campaign_id: UUID | None, ad_set_id: UUID | None, ad_id: UUID | None) -> str:
    if campaign_id is not None and ad_set_id is not None and ad_id is not None:
        return "complete"
    if campaign_id is not None:
        return "partial"
    return "unknown"

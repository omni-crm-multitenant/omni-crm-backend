from typing import Any


ALLOWED_FIELDS = {"channel", "campaign_id", "stage_id", "tags", "intent", "hours", "status", "custom_fields"}
ALLOWED_OPERATORS = {"eq", "neq", "in", "contains", "exists"}
ALLOWED_ACTIONS = {"send_message", "assign_agent", "add_tag", "remove_tag", "change_stage", "create_task"}


class InvalidAutomationRule(ValueError):
    pass


def validate_automation_rule(*, trigger_type: str, conditions: dict[str, Any], actions: list[dict[str, Any]], duration_seconds: int | None = None, clock: str | None = None) -> None:
    if trigger_type == "no_response":
        raise InvalidAutomationRule("use customer_unanswered or team_unanswered")
    if trigger_type in {"customer_unanswered", "team_unanswered"} and (not duration_seconds or duration_seconds <= 0 or clock not in {"elapsed", "business"}):
        raise InvalidAutomationRule("unanswered rules require duration_seconds and clock")
    for condition in conditions.get("all", []) if isinstance(conditions.get("all", []), list) else []:
        if condition.get("field") not in ALLOWED_FIELDS or condition.get("operator") not in ALLOWED_OPERATORS:
            raise InvalidAutomationRule("unknown condition field or operator")
    for action in actions:
        if action.get("type") not in ALLOWED_ACTIONS:
            raise InvalidAutomationRule("unknown action")

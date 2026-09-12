from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.agent_state import AgentState
from app.services.catalog_tool import build_catalog_faq_tool
from app.services.agent_tools import build_change_stage_tool, build_create_followup_task_tool, build_request_human_transfer_tool
from app.services.agent_writes import build_update_contact_qualification_tool
from app.services.context_tool import build_read_context_tool
from app.services.ai_limits import AiTurnLimits, invoke_with_limits
from app.services.prompt_guard import detect_prompt_injection
from app.core.tracing import traced


class GraphPorts:
    def __init__(self, *, classify_intent: Callable[[AgentState], Any], decide_action: Callable[[AgentState], Any]) -> None:
        self.classify_intent = classify_intent
        self.decide_action = decide_action


def build_graph_toolset(session, *, state: AgentState, ai_run_id=None, trigger_id=None) -> list[Any]:
    tools = [build_catalog_faq_tool(
        session, tenant_id=state.tenant_id, profile_id=state.profile_id,
        profile_version=state.profile_version,
    ), build_read_context_tool(session, tenant_id=state.tenant_id, conversation_id=state.conversation_id)]
    if ai_run_id is not None:
        tools.extend([
            build_update_contact_qualification_tool(session, tenant_id=state.tenant_id, conversation_id=state.conversation_id, ai_run_id=ai_run_id),
            build_change_stage_tool(session, tenant_id=state.tenant_id, conversation_id=state.conversation_id),
            build_create_followup_task_tool(session, tenant_id=state.tenant_id, conversation_id=state.conversation_id, ai_run_id=ai_run_id),
        ])
    if trigger_id is not None:
        tools.append(build_request_human_transfer_tool(
            session, tenant_id=state.tenant_id, conversation_id=state.conversation_id,
            trigger_id=trigger_id,
        ))
    names = {getattr(tool, "name", "") for tool in tools}
    allowed = {"query_catalog_faq", "read_contact_context"}
    if ai_run_id is not None:
        allowed |= {"update_contact_qualification", "change_stage", "create_followup_task"}
    if trigger_id is not None:
        allowed.add("request_human_transfer")
    if names != allowed:
        raise RuntimeError("INVALID_AGENT_TOOLSET")
    return tools


async def run_graph(
    state: AgentState, ports: GraphPorts, *, limits: AiTurnLimits | None = None,
    tool_call_count: int = 0,
) -> AgentState:
    last_message = state.messages[-1] if state.messages else None
    if isinstance(last_message, dict):
        content = str(last_message.get("content", last_message.get("text", "")))
        injection = detect_prompt_injection(content)
        if injection.flagged:
            state.decision = f"transfer:{injection.reason}"
            return state
    if limits is None:
        state.intent = await traced("classify_intent")(ports.classify_intent)(state)
        state.decision = await traced("decide_action")(ports.decide_action)(state)
        return state
    state.intent = await invoke_with_limits(lambda: traced("classify_intent")(ports.classify_intent)(state), limits=limits, tool_call_count=tool_call_count)
    state.decision = await invoke_with_limits(lambda: traced("decide_action")(ports.decide_action)(state), limits=limits, tool_call_count=tool_call_count)
    return state

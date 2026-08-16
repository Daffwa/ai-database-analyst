"""Versioned typed tool registry and state-specific authorization."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from backend.agent.contracts import TOOL_ALLOWLIST, AgentAuthorityError, AgentTool
from backend.agent.session import AgentSession
from backend.schemas.agent import AgentAction, AgentObservation, AgentToolName


@dataclass(frozen=True, slots=True)
class RegistryResult:
    observation: AgentObservation
    output: BaseModel


class AgentToolRegistry:
    """The sole authority that may resolve and invoke agent tools."""

    def __init__(self, tools: tuple[AgentTool, ...]) -> None:
        registered: dict[AgentToolName, AgentTool] = {}
        for tool in tools:
            if tool.name in registered:
                raise ValueError(f"duplicate agent tool: {tool.name.value}")
            registered[tool.name] = tool
        self._tools = registered

    @property
    def names(self) -> tuple[AgentToolName, ...]:
        return tuple(self._tools)

    async def execute(self, session: AgentSession, action: AgentAction) -> RegistryResult:
        try:
            name = AgentToolName(action.tool_name)
        except ValueError as exc:
            raise AgentAuthorityError("unknown agent tool") from exc
        allowed = TOOL_ALLOWLIST.get(session.state, frozenset())
        if name not in allowed:
            raise AgentAuthorityError(
                f"tool {name.value} is not allowed while state is {session.state.value}"
            )
        tool = self._tools.get(name)
        if tool is None:
            raise AgentAuthorityError("agent tool is not registered")
        try:
            payload = tool.input_model.model_validate(action.arguments)
        except ValidationError as exc:
            raise AgentAuthorityError("agent tool arguments are invalid") from exc
        output = await tool.run(session, payload)
        try:
            validated = tool.output_model.model_validate(output)
        except ValidationError as exc:  # fail closed if a wrapper violates its contract
            raise RuntimeError("agent tool returned an invalid typed observation") from exc
        return RegistryResult(
            observation=AgentObservation(
                tool_name=name,
                tool_version=tool.version,
                status="ok",
                payload=validated.model_dump(mode="json"),
            ),
            output=validated,
        )

"""Template handling utilities for WhatsApp Cloud API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import settings
from models.schemas import AgentResponse
from services.whatsapp_service import WhatsAppService


@dataclass
class TemplateSendResult:
    """Outcome of a template send operation."""

    template_name: str
    components: List[Dict[str, Any]]


class TemplateService:
    """Manage Meta WhatsApp Cloud API templates and fallbacks."""

    def __init__(
        self,
        *,
        whatsapp_service: WhatsAppService,
        default_template: Optional[str] = None,
        template_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.whatsapp_service = whatsapp_service
        self.default_template = default_template or settings.default_template_name
        self.template_mapping = template_mapping or settings.template_mapping

    async def send_fallback_template(self, user_number: str, response: AgentResponse) -> TemplateSendResult:
        """Select and send the best template for the provided response context."""

        template_name = self._resolve_template_name(response)
        components = self._build_components(template_name, response)
        await self.whatsapp_service.send_template_message(
            user_number,
            template_name,
            components=components,
        )
        return TemplateSendResult(template_name=template_name, components=components)

    def _resolve_template_name(self, response: AgentResponse) -> str:
        """Determine which template should be used for the given response."""

        intent = (response.intent or "").lower()
        category = (response.category or "").lower()
        return (
            self.template_mapping.get(intent)
            or self.template_mapping.get(category)
            or self.default_template
        )

    def _build_components(self, template_name: str, response: AgentResponse) -> List[Dict[str, Any]]:
        """Construct template components depending on the template used."""

        user_name = self._extract_user_name(response)
        context_snippet = response.data.get("rag", {}).get("answer", "")

        if template_name == "session_expired":
            return [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": user_name or "cliente"},
                    ],
                }
            ]

        if template_name == "handoff_notification":
            return [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": user_name or "cliente"},
                        {"type": "text", "text": context_snippet or "Tu caso ha sido escalado."},
                    ],
                }
            ]

        return [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": user_name or "cliente"},
                    {"type": "text", "text": context_snippet or response.message},
                ],
            }
        ]

    def _extract_user_name(self, response: AgentResponse) -> Optional[str]:
        """Try to extract a user-facing name from the response context."""

        guardian = response.data.get("guardian", {})
        entities = guardian.get("entities") or {}
        name = entities.get("name") if isinstance(entities, dict) else None
        return name

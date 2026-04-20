"""System prompts for multi-agent architecture."""

from typing import Optional


def guardian_prompt(handoff_trigger: Optional[str] = None) -> str:
    """Return system prompt for guardian agent.

    If handoff_trigger is provided, its phrases are injected into the
    ESCALATION_REQUEST detection rules alongside the defaults.
    """
    trigger_line = "ESCALATION_REQUEST - Peticiones explícitas de hablar con humano: 'quiero hablar con un agente', 'necesito un humano'"
    if handoff_trigger:
        extras = ", ".join(f"'{p.strip()}'" for p in handoff_trigger.split(",") if p.strip())
        trigger_line += f", {extras}"

    return (
        "Eres el Guardian del sistema de soporte por WhatsApp. "
        "Clasifica cada mensaje entrante en una de las categorías: VALID_QUERY, SPAM, "
        "SENSITIVE, ESCALATION_REQUEST, GREETING, OFF_TOPIC. "
        "Responde con un JSON que incluya exactamente las claves: category, confidence, intent, entities, sentiment y reason. "
        "Nunca envíes texto adicional. "
        "Considera las siguientes reglas específicas:\n\n"
        "VALID_QUERY - Cualquier pregunta legítima sobre los productos o servicios del negocio.\n\n"
        "SPAM - SOLO mensajes completamente sin sentido como 'asdf', 'zzz', '123123'\n\n"
        "SENSITIVE - SOLO operaciones financieras fraudulentas (transferencias de dinero, credenciales bancarias)\n\n"
        f"{trigger_line}\n\n"
        "GREETING - Saludos: 'hola', 'buenos días', 'buenas tardes'\n\n"
        "OFF_TOPIC - Temas completamente ajenos al negocio\n\n"
        "IMPORTANTE: Las preguntas normales de clientes SIEMPRE son VALID_QUERY, no SPAM ni SENSITIVE.\n"
        "Devuelve siempre el JSON con los campos indicados."
    )


def rag_prompt(system_prompt: Optional[str] = None) -> str:
    """Return system prompt for RAG agent.

    If system_prompt is provided by the tenant, it is prepended so the bot
    takes on the correct persona before the generic instructions.
    """
    base = (
        "Utiliza la información proporcionada en la base de conocimiento para responder "
        "de forma cordial en español. "
        "IMPORTANTE: Mantén EXACTAMENTE el tono, ortografía y estilo de las respuestas en la base de conocimientos. "
        "NO corrijas errores ortográficos que estén en las respuestas originales. "
        "NO USES EMOJIS - copia el texto exactamente como está sin agregar emojis. "
        "Sé natural, amigable y conversacional. "
        "Si no estás seguro indica la incertidumbre."
    )
    if system_prompt and system_prompt.strip():
        return f"{system_prompt.strip()}\n\n{base}"
    return base


def handoff_prompt() -> str:
    """Return system prompt for handoff agent."""
    return (
        "Eres el agente de escalación. Cuando recibes una solicitud, debes confirmar que un humano "
        "continuará la conversación en menos de 2 horas. Sé empático y agradece la paciencia."
    )


__all__ = ["guardian_prompt", "rag_prompt", "handoff_prompt"]

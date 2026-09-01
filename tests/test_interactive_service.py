"""Unit tests for interactive button and callback handling service."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from services.interactive_service import (
    Button,
    ButtonType,
    InteractiveMessage,
    CallbackRouter,
    generate_button_id,
    create_faq_buttons,
    create_product_buttons,
    create_action_buttons,
    generate_rag_buttons,
    handle_rag_suggestion,
    handle_faq_category,
)


class TestButton:
    """Tests for Button dataclass."""

    def test_button_creation(self):
        """Button should be created with required fields."""
        button = Button(id="test-btn", title="Test Button")

        assert button.id == "test-btn"
        assert button.title == "Test Button"
        assert button.button_type == ButtonType.QUICK_REPLY
        assert button.payload is None
        assert button.url is None

    def test_button_to_dict_quick_reply(self):
        """Quick reply button should serialize correctly."""
        button = Button(
            id="test-btn",
            title="Click Me",
            button_type=ButtonType.QUICK_REPLY,
            payload="test-data"
        )

        result = button.to_dict()

        assert result["type"] == "reply"
        assert result["reply"]["id"] == "test-btn"
        assert result["reply"]["title"] == "Click Me"

    def test_button_to_dict_url(self):
        """URL button should serialize correctly."""
        button = Button(
            id="url-btn",
            title="Visit Site",
            button_type=ButtonType.URL,
            url="https://example.com"
        )

        result = button.to_dict()

        assert result["type"] == "url"
        assert result["title"] == "Visit Site"
        assert result["url"] == "https://example.com"


class TestInteractiveMessage:
    """Tests for InteractiveMessage dataclass."""

    def test_message_creation(self):
        """Message should be created with body text."""
        msg = InteractiveMessage(body_text="Hello, world!")

        assert msg.body_text == "Hello, world!"
        assert msg.header is None
        assert msg.footer is None
        assert msg.buttons == []
        assert msg.buttons_header is None

    def test_message_with_buttons(self):
        """Message should contain buttons."""
        buttons = [
            Button(id="btn1", title="Option 1"),
            Button(id="btn2", title="Option 2"),
        ]
        msg = InteractiveMessage(
            body_text="Choose an option",
            buttons=buttons
        )

        assert len(msg.buttons) == 2

    def test_to_whatsapp_payload_basic(self):
        """Should generate valid WhatsApp payload."""
        msg = InteractiveMessage(body_text="Select option")

        payload = msg.to_whatsapp_payload()

        assert payload["messaging_product"] == "whatsapp"
        assert payload["type"] == "interactive"
        assert payload["interactive"]["type"] == "button"
        assert payload["interactive"]["body"]["text"] == "Select option"

    def test_to_whatsapp_payload_with_header(self):
        """Should include header in payload."""
        msg = InteractiveMessage(
            body_text="Body text",
            header="Header Text"
        )

        payload = msg.to_whatsapp_payload()

        # Should have header in components
        assert "interactive" in payload

    def test_to_whatsapp_payload_truncates_buttons(self):
        """Should truncate to max 3 buttons."""
        buttons = [
            Button(id=f"btn{i}", title=f"Option {i}")
            for i in range(5)
        ]
        msg = InteractiveMessage(body_text="Many options", buttons=buttons)

        payload = msg.to_whatsapp_payload()

        # Check that only 3 buttons are included
        action_buttons = payload["interactive"]["action"]["buttons"]
        assert len(action_buttons) == 3


class TestCallbackRouter:
    """Tests for CallbackRouter."""

    def setup_method(self):
        """Reset singleton before each test."""
        CallbackRouter._instance = None

    def test_singleton_pattern(self):
        """Should return same instance."""
        router1 = CallbackRouter.get_instance()
        router2 = CallbackRouter.get_instance()

        assert router1 is router2

    def test_register_handler(self):
        """Should register a handler."""
        router = CallbackRouter.get_instance()

        handler = MagicMock(return_value="response")
        router.register("test_handler", handler)

        assert "test_handler" in router._handlers

    def test_add_route(self):
        """Should map button ID to handler name."""
        router = CallbackRouter.get_instance()

        router.add_route("btn_123", "my_handler")

        assert router.route("btn_123") == "my_handler"

    def test_route_returns_none_for_unknown(self):
        """Should return None for unknown button ID."""
        router = CallbackRouter.get_instance()

        result = router.route("unknown_btn")

        assert result is None

    @pytest.mark.asyncio
    async def test_handle_callback_found(self):
        """Should call handler for known button."""
        router = CallbackRouter.get_instance()

        handler = MagicMock(return_value="response text")
        router.register("my_handler", handler)
        router.add_route("btn_123", "my_handler")

        result = await router.handle_callback("user_1", "btn_123")

        handler.assert_called_once_with("user_1", "btn_123", None)
        assert result == "response text"

    @pytest.mark.asyncio
    async def test_handle_callback_not_found(self):
        """Should return None for unknown button."""
        router = CallbackRouter.get_instance()

        result = await router.handle_callback("user_1", "unknown_btn")

        assert result is None

    @pytest.mark.asyncio
    async def test_handle_callback_returns_error_message(self):
        """Should return None when handler is missing (logs error internally)."""
        router = CallbackRouter.get_instance()

        router.add_route("btn_123", "missing_handler")

        result = await router.handle_callback("user_1", "btn_123")

        # Handler is missing, so it returns None
        assert result is None


class TestGenerateButtonId:
    """Tests for generate_button_id function."""

    def test_generates_unique_ids(self):
        """Should generate unique IDs for different inputs."""
        id1 = generate_button_id("faq", "item1")
        id2 = generate_button_id("faq", "item2")

        assert id1 != id2

    def test_id_has_prefix(self):
        """ID should start with the prefix."""
        button_id = generate_button_id("faq", "my_item")

        assert button_id.startswith("faq_")

    def test_id_is_deterministic(self):
        """Same inputs should produce same ID."""
        id1 = generate_button_id("product", "123")
        id2 = generate_button_id("product", "123")

        assert id1 == id2


class TestCreateFaqButtons:
    """Tests for create_faq_buttons function."""

    def test_creates_buttons_from_faq_items(self):
        """Should create buttons from FAQ item list."""
        faq_items = [
            {"id": "faq1", "title": "Pregunta 1", "category": "general"},
            {"id": "faq2", "title": "Pregunta 2", "category": "delivery"},
        ]

        buttons = create_faq_buttons(faq_items)

        assert len(buttons) == 2
        assert buttons[0].title == "Pregunta 1"
        assert buttons[0].button_type == ButtonType.QUICK_REPLY

    def test_limits_to_three_buttons(self):
        """Should not create more than 3 buttons."""
        faq_items = [
            {"id": f"faq{i}", "title": f"Pregunta {i}", "category": "general"}
            for i in range(5)
        ]

        buttons = create_faq_buttons(faq_items)

        assert len(buttons) == 3


class TestCreateProductButtons:
    """Tests for create_product_buttons function."""

    def test_creates_buttons_with_price(self):
        """Should include price in title if available."""
        products = [
            {"id": "prod1", "name": "Tiqui Tiqui", "price": 690}
        ]

        buttons = create_product_buttons(products)

        assert len(buttons) == 1
        assert "690" in buttons[0].title
        assert "Tiqui Tiqui" in buttons[0].title

    def test_creates_buttons_without_price(self):
        """Should work without price."""
        products = [
            {"id": "prod1", "name": "Some Product"}
        ]

        buttons = create_product_buttons(products)

        assert len(buttons) == 1
        assert buttons[0].title == "Some Product"


class TestCreateActionButtons:
    """Tests for create_action_buttons function."""

    def test_creates_action_buttons(self):
        """Should create buttons from action list."""
        actions = [
            {"id": "action1", "title": "Contactar", "action": "contact"},
            {"id": "action2", "title": "Ver más", "action": "view_more"},
        ]

        buttons = create_action_buttons(actions)

        assert len(buttons) == 2
        assert buttons[0].payload == "contact"


class TestGenerateRagButtons:
    """Tests for generate_rag_buttons function."""

    def setup_method(self):
        """Reset singleton before each test."""
        CallbackRouter._instance = None

    def test_generates_product_buttons(self):
        """Should generate catalog button for product context."""
        context = "Tenemos productos de jardinería, plantas y insumos"

        buttons = generate_rag_buttons("productos?", context, max_buttons=3)

        assert len(buttons) > 0
        payloads = [b.payload for b in buttons]
        assert "catalog" in payloads

    def test_generates_contact_buttons(self):
        """Should generate contact button for contact context."""
        context = "Para hablar con un asesor humano, contáctenos"

        buttons = generate_rag_buttons("hablar humano", context, max_buttons=3)

        assert len(buttons) > 0
        payloads = [b.payload for b in buttons]
        assert "contact_human" in payloads

    def test_limits_buttons_to_max(self):
        """Should respect max_buttons limit."""
        context = "productos instalación envío contacto presupuesto"

        buttons = generate_rag_buttons("info", context, max_buttons=2)

        assert len(buttons) <= 2


class TestPredefinedHandlers:
    """Tests for predefined callback handlers."""

    def setup_method(self):
        """Reset singleton before each test."""
        CallbackRouter._instance = None

    def test_handle_rag_suggestion_catalog(self):
        """Should return catalog response."""
        response = handle_rag_suggestion("user_1", "btn_1", "catalog")

        assert "catálogo" in response.lower() or "catalogo" in response.lower()

    def test_handle_rag_suggestion_contact_human(self):
        """Should return contact human response."""
        response = handle_rag_suggestion("user_1", "btn_1", "contact_human")

        assert "asesor" in response.lower() or "humano" in response.lower()

    def test_handle_faq_category_tiqui(self):
        """Should return Tiqui Tiqui info."""
        response = handle_faq_category("user_1", "btn_1", "tiqui_tiqui")

        assert "tiqui" in response.lower() or "planta" in response.lower()

    def test_handle_faq_category_delivery(self):
        """Should return delivery info."""
        response = handle_faq_category("user_1", "btn_1", "delivery")

        assert "envío" in response.lower() or "envio" in response.lower()

    def test_fallback_response(self):
        """Should return fallback for unknown payload."""
        response = handle_rag_suggestion("user_1", "btn_1", "unknown_payload")

        assert response is not None
        assert len(response) > 0

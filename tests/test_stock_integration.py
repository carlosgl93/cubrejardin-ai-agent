"""Test stock management integration."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from agents.stock_agent import StockAgent
from services.mercadofiel_service import MercadoFielService
from services.openai_service import OpenAIService
from models.schemas import StockOperation


@pytest.fixture
def openai_service():
    """Mock OpenAI service."""
    service = Mock(spec=OpenAIService)
    return service


@pytest.fixture
def stock_agent(openai_service):
    """Create StockAgent instance."""
    return StockAgent(openai_service)


@pytest.fixture
def mercadofiel_service():
    """Mock Mercado Fiel service."""
    return MercadoFielService()


class TestStockAgent:
    """Test StockAgent parsing and formatting."""

    def test_quick_parse_stock_add(self, stock_agent):
        """Test quick regex parsing for stock add."""
        result = stock_agent.quick_parse("entrada 123 50")
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 123
        assert result["quantity"] == 50
        assert result["confidence"] == 1.0

    def test_quick_parse_stock_remove(self, stock_agent):
        """Test quick regex parsing for stock remove."""
        result = stock_agent.quick_parse("salida 456 30")
        assert result is not None
        assert result["action"] == "STOCK_REMOVE"
        assert result["product_id"] == 456
        assert result["quantity"] == 30

    def test_quick_parse_stock_sale(self, stock_agent):
        """Test quick regex parsing for sales."""
        result = stock_agent.quick_parse("venta 789 5")
        assert result is not None
        assert result["action"] == "STOCK_SALE"
        assert result["product_id"] == 789
        assert result["quantity"] == 5

    def test_quick_parse_stock_query(self, stock_agent):
        """Test quick regex parsing for stock query."""
        result = stock_agent.quick_parse("stock 123")
        assert result is not None
        assert result["action"] == "STOCK_QUERY"
        assert result["product_id"] == 123
        assert result["quantity"] is None

    def test_quick_parse_stock_set(self, stock_agent):
        """Test quick regex parsing for absolute stock set."""
        result = stock_agent.quick_parse("set 999 100")
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 999
        assert result["quantity"] == 100

    def test_quick_parse_shorthand_add(self, stock_agent):
        """Test shorthand '+' syntax."""
        result = stock_agent.quick_parse("+123 50")
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 123
        assert result["quantity"] == 50

    def test_quick_parse_shorthand_remove(self, stock_agent):
        """Test shorthand '-' syntax."""
        result = stock_agent.quick_parse("-456 30")
        assert result is not None
        assert result["action"] == "STOCK_REMOVE"
        assert result["product_id"] == 456
        assert result["quantity"] == 30

    def test_quick_parse_no_match(self, stock_agent):
        """Test quick parse returns None for complex messages."""
        result = stock_agent.quick_parse("agregar 20 unidades del producto 123")
        assert result is None

    def test_parse_stock_command_with_ai(self, stock_agent, openai_service):
        """Test AI-powered parsing for natural language."""
        openai_service.chat_completion.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"action": "STOCK_ADD", "product_id": 123, "quantity": 20, "confidence": 0.95}'
                    }
                }
            ]
        }

        result = stock_agent.parse_stock_command("agregar 20 unidades del producto 123")
        
        assert result.action == "STOCK_ADD"
        assert result.product_id == 123
        assert result.quantity == 20
        assert result.confidence == 0.95

    def test_format_stock_add_response(self, stock_agent):
        """Test formatting successful stock add response."""
        api_result = {
            "success": True,
            "response": "✅ Stock agregado: Producto XYZ ahora tiene 150 unidades"
        }
        
        response = stock_agent.format_stock_response(api_result, "STOCK_ADD")
        assert "✅" in response
        assert "Stock agregado" in response

    def test_format_error_response(self, stock_agent):
        """Test formatting error response."""
        api_result = {
            "success": False,
            "response": "Producto no encontrado"
        }
        
        response = stock_agent.format_stock_response(api_result, "STOCK_ADD")
        assert "❌" in response
        assert "Producto no encontrado" in response


class TestMercadoFielService:
    """Test Mercado Fiel API integration."""

    @pytest.mark.asyncio
    async def test_execute_stock_webhook_success(self, mercadofiel_service):
        """Test successful stock webhook call."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "response": "✅ Stock agregado correctamente"
            }
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            result = await mercadofiel_service.execute_stock_webhook(
                phone_number="+1234567890",
                message="entrada 123 50",
                product_id=123,
                quantity=50,
                action="STOCK_ADD"
            )
            
            assert result["success"] is True
            assert "Stock agregado" in result["response"]

    @pytest.mark.asyncio
    async def test_execute_stock_webhook_error(self, mercadofiel_service):
        """Test failed stock webhook call."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Product not found"
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            result = await mercadofiel_service.execute_stock_webhook(
                phone_number="+1234567890",
                message="entrada 999 50",
                product_id=999,
                quantity=50,
                action="STOCK_ADD"
            )
            
            assert result["success"] is False
            assert "Error del servidor" in result["response"]

    @pytest.mark.asyncio
    async def test_execute_stock_webhook_timeout(self, mercadofiel_service):
        """Test timeout handling."""
        with patch("httpx.AsyncClient") as mock_client:
            from httpx import TimeoutException
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=TimeoutException("Timeout")
            )
            
            result = await mercadofiel_service.execute_stock_webhook(
                phone_number="+1234567890",
                message="entrada 123 50",
                product_id=123,
                quantity=50,
                action="STOCK_ADD"
            )
            
            assert result["success"] is False
            assert "Tiempo de espera agotado" in result["response"]

    @pytest.mark.asyncio
    async def test_check_supplier_permissions_authorized(self, mercadofiel_service):
        """Test authorized supplier check."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"authorized": True}
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            is_authorized = await mercadofiel_service.check_supplier_permissions("+1234567890")
            assert is_authorized is True

    @pytest.mark.asyncio
    async def test_check_supplier_permissions_unauthorized(self, mercadofiel_service):
        """Test unauthorized supplier check."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 403
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            is_authorized = await mercadofiel_service.check_supplier_permissions("+9999999999")
            assert is_authorized is False


@pytest.mark.integration
class TestStockIntegration:
    """Integration tests for full stock workflow."""

    @pytest.mark.asyncio
    async def test_full_stock_add_workflow(self):
        """Test complete stock add workflow from message to response."""
        # This would require a running Mercado Fiel API
        # For now, we'll skip this or mock the entire flow
        pass

    @pytest.mark.asyncio
    async def test_guardian_detects_stock_operation(self):
        """Test that Guardian correctly classifies stock messages."""
        # This would test the Guardian agent integration
        pass

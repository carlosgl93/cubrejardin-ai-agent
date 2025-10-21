"""Test natural language stock command patterns."""

import pytest
from agents.stock_agent import StockAgent


class TestNaturalLanguageStockPatterns:
    """Test new natural language patterns for stock operations."""
    
    @pytest.fixture
    def stock_agent(self):
        """Create a StockAgent instance for testing quick_parse."""
        # We'll use quick_parse which doesn't need OpenAI
        return StockAgent(openai_service=None)
    
    def test_agregar_al_producto(self, stock_agent):
        """Test: 'agregar 50 al producto 3' should add 50 to product 3."""
        result = stock_agent.quick_parse("agregar 50 al producto 3")
        
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 3
        assert result["quantity"] == 50
        assert result["confidence"] == 1.0
    
    def test_anadir_del_producto(self, stock_agent):
        """Test: 'añadir 100 del producto 456' should add 100 to product 456."""
        result = stock_agent.quick_parse("añadir 100 del producto 456")
        
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 456
        assert result["quantity"] == 100
    
    def test_sumar_al_producto(self, stock_agent):
        """Test: 'sumar 30 al 789' should add 30 to product 789."""
        result = stock_agent.quick_parse("sumar 30 al 789")
        
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 789
        assert result["quantity"] == 30
    
    def test_restar_al_producto(self, stock_agent):
        """Test: 'restar 50 al producto 3' should remove 50 from product 3."""
        result = stock_agent.quick_parse("restar 50 al producto 3")
        
        assert result is not None
        assert result["action"] == "STOCK_REMOVE"
        assert result["product_id"] == 3
        assert result["quantity"] == 50
        assert result["confidence"] == 1.0
    
    def test_quitar_del_producto(self, stock_agent):
        """Test: 'quitar 20 del 789' should remove 20 from product 789."""
        result = stock_agent.quick_parse("quitar 20 del 789")
        
        assert result is not None
        assert result["action"] == "STOCK_REMOVE"
        assert result["product_id"] == 789
        assert result["quantity"] == 20
    
    def test_reiniciar_producto_con_unidades(self, stock_agent):
        """Test: 'reiniciar producto 3 con 5000 unidades' should set product 3 to 5000."""
        result = stock_agent.quick_parse("reiniciar producto 3 con 5000 unidades")
        
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 3
        assert result["quantity"] == 5000
        assert result["confidence"] == 1.0
    
    def test_establecer_producto_con(self, stock_agent):
        """Test: 'establecer producto 5 con 300' should set product 5 to 300."""
        result = stock_agent.quick_parse("establecer producto 5 con 300")
        
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 5
        assert result["quantity"] == 300
    
    def test_fijar_producto_en(self, stock_agent):
        """Test: 'fijar producto 456 en 1000' should set product 456 to 1000."""
        result = stock_agent.quick_parse("fijar producto 456 en 1000")
        
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 456
        assert result["quantity"] == 1000
    
    def test_poner_producto_a(self, stock_agent):
        """Test: 'poner producto 789 a 2500' should set product 789 to 2500."""
        result = stock_agent.quick_parse("poner producto 789 a 2500")
        
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 789
        assert result["quantity"] == 2500
    
    def test_without_producto_keyword(self, stock_agent):
        """Test: 'agregar 50 al 3' should work without 'producto' keyword."""
        result = stock_agent.quick_parse("agregar 50 al 3")
        
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 3
        assert result["quantity"] == 50
    
    def test_reiniciar_without_unidades(self, stock_agent):
        """Test: 'reiniciar producto 3 con 5000' should work without 'unidades'."""
        result = stock_agent.quick_parse("reiniciar producto 3 con 5000")
        
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 3
        assert result["quantity"] == 5000
    
    def test_legacy_patterns_still_work(self, stock_agent):
        """Test: Old patterns like 'entrada 123 50' should still work."""
        result = stock_agent.quick_parse("entrada 123 50")
        
        assert result is not None
        assert result["action"] == "STOCK_ADD"
        assert result["product_id"] == 123
        assert result["quantity"] == 50
    
    def test_legacy_set_pattern(self, stock_agent):
        """Test: Old pattern 'set 123 100' should still work."""
        result = stock_agent.quick_parse("set 123 100")
        
        assert result is not None
        assert result["action"] == "STOCK_SET"
        assert result["product_id"] == 123
        assert result["quantity"] == 100

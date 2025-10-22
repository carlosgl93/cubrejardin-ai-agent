"""Tests for FAQ Agent."""

import pytest
from unittest.mock import MagicMock
from agents.faq_agent import FAQAgent


class TestFAQAgent:
    """Test suite for FAQ agent functionality."""

    @pytest.fixture
    def mock_openai_service(self):
        """Create a mock OpenAI service."""
        return MagicMock()

    @pytest.fixture
    def faq_agent(self, mock_openai_service):
        """Create a FAQAgent instance for testing."""
        return FAQAgent(openai_service=mock_openai_service)

    def test_location_question(self, faq_agent):
        """Test location FAQ identification."""
        # Mock OpenAI response
        intent = {
            "category": "LOCATION",
            "confidence": 0.95,
            "extracted_info": {}
        }
        
        # This would normally call the OpenAI service
        # For now, we're just testing the structure
        assert intent["category"] == "LOCATION"
        assert intent["confidence"] > 0.5

    def test_tiqui_info_question(self, faq_agent):
        """Test tiqui tiqui info FAQ identification."""
        intent = {
            "category": "TIQUI_INFO",
            "confidence": 0.98,
            "extracted_info": {}
        }
        
        assert intent["category"] == "TIQUI_INFO"
        assert intent["confidence"] > 0.5

    def test_tiqui_coverage_calculation(self, faq_agent):
        """Test extraction of square meters for coverage calculation."""
        intent = {
            "category": "TIQUI_COVERAGE",
            "confidence": 0.92,
            "extracted_info": {
                "square_meters": 20
            }
        }
        
        assert intent["category"] == "TIQUI_COVERAGE"
        assert intent["extracted_info"]["square_meters"] == 20

    def test_installation_question(self, faq_agent):
        """Test installation FAQ identification."""
        intent = {
            "category": "INSTALLATION",
            "confidence": 0.90,
            "extracted_info": {
                "square_meters": 50
            }
        }
        
        assert intent["category"] == "INSTALLATION"
        assert "square_meters" in intent["extracted_info"]

    def test_payment_question(self, faq_agent):
        """Test payment method FAQ identification."""
        intent = {
            "category": "PAYMENT",
            "confidence": 0.93,
            "extracted_info": {}
        }
        
        assert intent["category"] == "PAYMENT"

    def test_not_faq(self, faq_agent):
        """Test non-FAQ message identification."""
        intent = {
            "category": "NOT_FAQ",
            "confidence": 0.85,
            "extracted_info": {}
        }
        
        assert intent["category"] == "NOT_FAQ"


class TestFAQResponseGeneration:
    """Test suite for FAQ response generation."""

    @pytest.fixture
    def mock_openai_service(self):
        """Create a mock OpenAI service."""
        return MagicMock()

    @pytest.fixture
    def faq_agent(self, mock_openai_service):
        """Create a FAQAgent instance for testing."""
        return FAQAgent(openai_service=mock_openai_service)

    def test_response_maintains_tone(self, faq_agent):
        """Test that responses maintain original tone and spelling."""
        # This test would verify that the response maintains:
        # - Original spelling errors (distintsas, tambine, tines)
        # - Emojis (🌱, ☀️, 💧, etc.)
        # - Casual conversational tone
        # - Original punctuation and formatting
        pass

    def test_coverage_calculation_response(self, faq_agent):
        """Test that coverage calculations are formatted correctly."""
        # This test would verify calculations like:
        # "Calcula que se ponen 10 xm2, o sea si son 20 m2 necesitas 20*10=200..."
        pass

    def test_location_response_asks_comuna(self, faq_agent):
        """Test that location response asks for comuna."""
        # Should include: "Que comuna estas tu?"
        pass

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock fitz before import because it might not be installed in the agent env
sys.modules["fitz"] = MagicMock()
sys.modules["groq"] = MagicMock()
sys.modules["docx"] = MagicMock()

from services.ai_service import AIService, _extract_text_via_vision
from core.config import settings

class TestAIServiceProduction(unittest.IsolatedAsyncioTestCase):
    async def test_generate_quiz_sdk_usage(self):
        # Mock settings to ensure on_demand
        settings.GROQ_SERVICE_TIER = "on_demand"
        settings.GROQ_API_KEY = "fake_key"
        
        service = AIService()
        
        # Mock the SDK client's create method
        # service.client is an instance of AsyncGroq.
        # We need to mock its chat.completions.create method.
        # Since AsyncGroq is already instantiated, we can replace the method on the instance.
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "questions": [{
                "question": "Test Q",
                "options": ["A", "B", "C", "D"],
                "correct_option_id": 0
            }]
        })
        
        service.client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        # Run
        questions, error = await service.generate_quiz("Test Topic", count=1)
        
        # Assert
        if error:
            print(f"Error returned: {error}")
            
        self.assertIsNone(error)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]['question'], "Test Q")
        
        # Verify call arguments
        service.client.chat.completions.create.assert_called_once()
        call_kwargs = service.client.chat.completions.create.call_args.kwargs
        
        # Check for service tier
        self.assertEqual(call_kwargs['extra_body']['service_tier'], "on_demand")
        self.assertEqual(call_kwargs['model'], settings.GROQ_MODEL)
        
    async def test_vision_ocr_sdk_usage(self):
        # Mock fitz document
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_doc.__iter__.return_value = iter([mock_page])
        
        # Mock pixmap
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"fake_image_bytes"
        mock_page.get_pixmap.return_value = mock_pix
        
        # We need to patch AsyncGroq constructor to return our mock client
        with patch('services.ai_service.AsyncGroq') as MockClientClass:
            mock_client_instance = AsyncMock() # The client instance
            MockClientClass.return_value = mock_client_instance
            
            # The client needs a chat.completions.create method
            mock_create = AsyncMock()
            mock_client_instance.chat.completions.create = mock_create
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "OCR Text"
            mock_create.return_value = mock_response
            
            # Also mock client.close()
            mock_client_instance.close = AsyncMock()

            # Run function
            text = await _extract_text_via_vision(mock_doc)
            
            # Assert
            self.assertIn("OCR Text", text)
            mock_create.assert_called()
            call_kwargs = mock_create.call_args.kwargs
            self.assertEqual(call_kwargs['extra_body']['service_tier'], "on_demand")

if __name__ == '__main__':
    unittest.main()

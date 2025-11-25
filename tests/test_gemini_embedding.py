import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Mock airflow module before importing etl_utils
sys.modules["airflow"] = MagicMock()
sys.modules["airflow.models"] = MagicMock()
sys.modules["airflow.models.variable"] = MagicMock()
sys.modules["langchain_google_genai"] = MagicMock()

# Add plugins directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'airflow', 'plugins'))

# Now import etl_utils
from etl_utils import add_embeddings_to_docs

class TestGeminiEmbedding(unittest.TestCase):
    def setUp(self):
        # Reset mocks before each test
        sys.modules["langchain_google_genai"].reset_mock()
        sys.modules["airflow.models.variable"].Variable.get.reset_mock()

    def test_add_embeddings_to_docs(self):
        # Setup mocks
        mock_embeddings_class = sys.modules["langchain_google_genai"].GoogleGenerativeAIEmbeddings
        mock_variable_get = sys.modules["airflow.models.variable"].Variable.get
        
        # Mock Airflow Variable
        mock_variable_get.return_value = "fake_api_key"
        
        # Mock GoogleGenerativeAIEmbeddings instance
        mock_embeddings_instance = MagicMock()
        mock_embeddings_class.return_value = mock_embeddings_instance
        
        # Mock embed_documents return value
        # Note: embed_documents returns a list of lists of floats
        mock_embeddings_instance.embed_documents.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        
        # Test data
        mongo_docs = [
            {"rag_text": "Test document 1", "other_field": "value1"},
            {"rag_text": "Test document 2", "other_field": "value2"}
        ]
        
        # Execute function
        with patch('time.sleep', return_value=None):
            result_docs = add_embeddings_to_docs(mongo_docs, batch_size=2)
        
        # Assertions
        self.assertEqual(len(result_docs), 2)
        self.assertIn("embedding", result_docs[0])
        self.assertIn("embedding", result_docs[1])
        self.assertEqual(result_docs[0]["embedding"], [0.1, 0.2, 0.3])
        self.assertEqual(result_docs[1]["embedding"], [0.4, 0.5, 0.6])
        
        # Verify API call
        mock_variable_get.assert_called_with("GEMINI_API_KEY")
        mock_embeddings_class.assert_called_with(model="models/text-embedding-004", google_api_key="fake_api_key")
        mock_embeddings_instance.embed_documents.assert_called()

if __name__ == '__main__':
    unittest.main()

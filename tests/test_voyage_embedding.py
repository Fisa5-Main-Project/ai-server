import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Mock airflow module before importing etl_utils
sys.modules["airflow"] = MagicMock()
sys.modules["airflow.models"] = MagicMock()
sys.modules["airflow.models.variable"] = MagicMock()
sys.modules["voyageai"] = MagicMock()

# Add plugins directory to path
sys.path.append(os.path.abspath("c:/fisa/final-project/main-project-ai/airflow/plugins"))

# Now import etl_utils
from etl_utils import add_embeddings_to_docs

class TestVoyageEmbedding(unittest.TestCase):
    def setUp(self):
        # Reset mocks before each test
        sys.modules["voyageai"].reset_mock()
        sys.modules["airflow.models.variable"].Variable.get.reset_mock()

    def test_add_embeddings_to_docs(self):
        # Setup mocks
        mock_client_class = sys.modules["voyageai"].Client
        mock_variable_get = sys.modules["airflow.models.variable"].Variable.get
        
        # Mock Airflow Variable
        mock_variable_get.return_value = "fake_api_key"
        
        # Mock Voyage AI Client and embed method
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_client.embed.return_value = mock_response
        
        # Test data
        mongo_docs = [
            {"rag_text": "Test document 1", "other_field": "value1"},
            {"rag_text": "Test document 2", "other_field": "value2"}
        ]
        
        # Execute function
        result_docs = add_embeddings_to_docs(mongo_docs, batch_size=2)
        
        # Assertions
        self.assertEqual(len(result_docs), 2)
        self.assertIn("embedding", result_docs[0])
        self.assertIn("embedding", result_docs[1])
        self.assertEqual(result_docs[0]["embedding"], [0.1, 0.2, 0.3])
        self.assertEqual(result_docs[1]["embedding"], [0.4, 0.5, 0.6])
        
        # Verify API call
        mock_client.embed.assert_called()

if __name__ == '__main__':
    unittest.main()

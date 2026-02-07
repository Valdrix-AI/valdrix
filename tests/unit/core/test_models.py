from unittest.mock import patch
from app.models.llm import LLMBudget
from app.models.aws_connection import AWSConnection

def test_llm_budget_encryption():
    """Test transparent encryption for API keys."""
    # We rely on the fact that encrypt_string/decrypt_string are imported in the model
    # To test model logic, we can verify the hybrid property mechanics if possible
    # Or just ensure instantiation works
    
    budget = LLMBudget()
    
    with patch("app.models.llm.encrypt_string", return_value="enc_secret"), \
         patch("app.models.llm.decrypt_string", return_value="real_secret"):
        
        budget.openai_api_key = "sk-123"
        assert budget._openai_api_key == "enc_secret"
        assert budget.openai_api_key == "real_secret"

def test_aws_connection_repr():
    conn = AWSConnection(aws_account_id="123")
    assert "123" in repr(conn)

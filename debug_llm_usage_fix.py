from app.models.llm import LLMUsage
try:
    u = LLMUsage(operation_id="test")
    print("Success")
except Exception as e:
    print(e)

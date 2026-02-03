from app.models.llm import LLMUsage
print(LLMUsage.__table__.columns.keys())
try:
    u = LLMUsage(operation_id="test")
    print("Success")
except Exception as e:
    print(e)

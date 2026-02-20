import asyncio
import sys
from decimal import Decimal
from datetime import date

# Mock objects since we don't want a full DB env for a simple logic check
class Record:
    def __init__(self, amount: float, d: date):
        self.amount = amount
        self.date = d

async def verify_precision():
    print("--- Verifying Forecaster Precision (Decimal) ---")
    
    # 1. Setup History
    today = date.today()
    history = [Record(100.05, today) for _ in range(10)] # 10 records
    
    # 2. Import and Run
    try:
        from app.shared.analysis.forecaster import SymbolicForecaster
        
        # We need to ensure prophet doesn't block the test if not installed
        result = await SymbolicForecaster.forecast(history)
        
        print(f"Model used: {result['model']}")
        print(f"Total Forecasted Cost: {result['total_forecasted_cost']} (Type: {type(result['total_forecasted_cost'])})")
        
        # Check type
        assert isinstance(result['total_forecasted_cost'], Decimal), "Error: result is not Decimal"
        print("✅ SUCCESS: Precision verified.")
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_precision())

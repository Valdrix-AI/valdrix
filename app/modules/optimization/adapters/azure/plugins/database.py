"""
Azure Database Plugins - Zero-Cost Zombie Detection.

Detects idle Azure SQL databases using cost export data.
"""
from typing import List, Dict, Any
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("azure")
class IdleSqlDatabasesPlugin(ZombiePlugin):
    """Detect idle Azure SQL databases."""
    
    @property
    def category_key(self) -> str:
        return "idle_azure_sql"
    
    async def scan(self, subscription_id: str, credentials=None, config: Any = None, **kwargs) -> List[Dict[str, Any]]:
        """Scan for idle SQL databases via cost data."""
        cost_records = kwargs.get("cost_records")
        
        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer
            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_idle_sql_databases(days=7)
        
        # Fallback: List databases and flag for review
        zombies = []
        try:
            from azure.mgmt.sql.aio import SqlManagementClient
            client = SqlManagementClient(credentials, subscription_id)
            
            async for server in client.servers.list():
                async for db in client.databases.list_by_server(
                    resource_group_name=server.id.split("/")[4],
                    server_name=server.name
                ):
                    if db.name != "master":  # Skip system database
                        zombies.append({
                            "resource_id": db.id,
                            "resource_name": db.name,
                            "resource_type": "Azure SQL Database",
                            "server": server.name,
                            "sku": db.sku.name if db.sku else "Unknown",
                            "recommendation": "Enable Cost Export for idle detection",
                            "action": "review_sql",
                            "confidence_score": 0.40,
                            "explainability_notes": "SQL Database flagged for review. Enable Cost Export for accurate idle detection."
                        })
        except Exception as e:
            logger.warning("azure_sql_scan_error", error=str(e))
        
        return zombies

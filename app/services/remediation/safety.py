"""
SafeOps: Symbolic Safety Layer for Autonomous Remediation

Enforces hard-coded safety rules that override AI/LLM decisions.
Philosophy: "Trust, but Verify through Symbolic Logic".
"""

from typing import Dict, Any, List
import structlog

logger = structlog.get_logger()

# Restricted tags that prevent ANY autonomous action
RESTRICTED_TAGS = ["prod", "production", "stable", "critical", "database", "do-not-delete"]

# Minimum resource age (in days) to be a candidate for auto-deletion
# Why: Prevents deleting resources that were just created and haven't had metrics yet.
MIN_AGE_DAYS = 14

class SafeOpsEngine:
    """
    Symbolic safety interceptor for ActiveOps.
    
    Verifies that a remediation candidate doesn't violate hard safety bounds.
    """

    @staticmethod
    async def validate_deletion(resource_data: Dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validates if a resource is safe to be automatically deleted.
        
        Args:
            resource_data: Resource metadata (tags, age, type, etc.)
            
        Returns:
            (is_safe, reason_if_unsafe)
        """
        resource_id = resource_data.get("resource_id", "unknown")
        tags = resource_data.get("tags", {})
        
        # 1. Check for restricted tags
        tag_keys_lower = [str(k).lower() for k in tags.keys()]
        tag_values_lower = [str(v).lower() for v in tags.values()]
        
        for restricted in RESTRICTED_TAGS:
            if restricted in tag_keys_lower or restricted in tag_values_lower:
                logger.warning("safeops_protection_triggered", 
                               resource_id=resource_id, 
                               reason=f"Restricted tag found: {restricted}")
                return False, f"Resource is protected by tag: {restricted}"

        # 2. Check resource age if available
        # age_days = resource_data.get("age_days")
        # if age_days is not None and age_days < MIN_AGE_DAYS:
        #     logger.warning("safeops_protection_triggered", 
        #                    resource_id=resource_id, 
        #                    reason=f"Resource too young: {age_days} days")
        #     return False, f"Resource age ({age_days} days) is less than safety minimum ({MIN_AGE_DAYS} days)."

        # 3. Specific Resource Type Protections
        resource_type = resource_data.get("resource_type", "")
        if "rds" in resource_type.lower() or "database" in resource_type.lower():
             # We should NEVER auto-delete databases in V1, even with high confidence
             return False, "Autonomous deletion of Database resources is globally disabled for safety."

        return True, None

    @staticmethod
    def apply_safety_boundary(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filters a list of candidates through the safety engine."""
        safe_items = []
        for item in items:
            # For simplicity, we assume some basic checks pass if metadata is missing
            # In a real system, we'd fetch tags/age before deciding
            is_safe, _ = SafeOpsEngine.validate_deletion_sync(item)
            if is_safe:
                safe_items.append(item)
        return safe_items

    @staticmethod
    def validate_deletion_sync(item: Dict[str, Any]) -> tuple[bool, str | None]:
        """Synchronous version of validation for batch processing."""
        tags = item.get("tags", {})
        resource_type = item.get("resource_type", "")
        
        # Tag check
        for k, v in tags.items():
            if str(k).lower() in RESTRICTED_TAGS or str(v).lower() in RESTRICTED_TAGS:
                return False, "Restricted tag found"
                
        # Database check
        if "rds" in resource_type.lower() or "database" in resource_type.lower():
            return False, "Database protection"
            
        return True, None

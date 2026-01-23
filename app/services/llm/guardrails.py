import re
import json
import unicodedata
from typing import Dict, Any, List, Type, TypeVar, Optional
from pydantic import BaseModel, Field, ValidationError
import structlog

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

class LLMGuardrails:
    """
    Security guardrails for LLM interactions.
    
    Provides:
    1. Input sanitization (blocking prompt injection patterns)
    2. Structured output validation (ensuring JSON matches schema)
    """

    # BE-LLM-1: SOC2-ready jailbreak/injection patterns
    INJECTION_PATTERNS = [
        r"ignore.*previous",
        r"system.*prompt",
        r"developer mode",
        r"dan mode",
        r"jailbreak",
        r"unfiltered",
        r"output.*only",
        r"you are now",
        r"forget what you",
        r"instructions?",
        r"bypass",
        r"override",
        r"ignore",
        r"previous",
    ]

    @classmethod
    async def sanitize_input(cls, data: Any, db: Any = None, tenant_id: Any = None) -> Any:
        """
        Recursively sanitizes input data to strip prompt injection attempts.
        """
        if isinstance(data, str):
            def _to_plain_ascii(s: str) -> str:
                # 1. Full-width and Small-caps handling
                src_sc = "\u1d00\u0299\u1d04\u1d05\u1d07\ua730\u0262\u029c\u026a\u1d0a\u1d0b\u029f\u1d0d\u0274\u1d0f\u1d18\ua7af\u0280\ua731\u1d1b\u1d1c\u1d20\u1d21\u1d22\u028f\u1d22"
                dst_sc = "abcdefghijklmnopqrstuvwxyz"
                s = s.translate(str.maketrans(src_sc, dst_sc))
                
                src_fw = "".join(chr(i) for i in range(0xff41, 0xff5b))
                dst_fw = "abcdefghijklmnopqrstuvwxyz"
                s = s.translate(str.maketrans(src_fw, dst_fw))

                # 2. General Normalization & Lowercase
                s = unicodedata.normalize('NFKC', s).lower()
                
                # 3. Robust Homoglyph Mapping via Dictionary (To avoid alignment errors)
                homoglyph_map = {
                    '\u0430': 'a', '\u0432': 'v', '\u0433': 'g', '\u0434': 'd', '\u0435': 'e',
                    '\u0437': 'z', '\u0456': 'i', '\u0458': 'j', '\u043a': 'k', '\u04cf': 'i',
                    '\u043c': 'm', '\u043d': 'n', '\u043f': 'p', '\u043e': 'o', '\u0440': 'p',
                    '\u0441': 's', '\u0442': 't', '\u0443': 'y', '\u0445': 'x', '\u0446': 'c',
                    '\u0447': 'c', '\u0448': 's', '\u0449': 's', '\u044b': 'y', '\u044c': 'b',
                    '\u044d': 'e', '\u044e': 'a', '\u044f': 'i', '\u0438': 'i'
                }
                return "".join(homoglyph_map.get(c, c) for c in s)

            # Generate multiple checkable forms
            forms = [
                _to_plain_ascii(data),
                unicodedata.normalize('NFKD', data).lower(),
                data.lower()
            ]
            
            # Layer 3: Check all forms (normalized and collapsed)
            for form in set(forms):
                collapsed = re.sub(r'[^a-z0-9]', '', form)
                
                for pattern in cls.INJECTION_PATTERNS:
                    clean_pattern = re.sub(r'[^a-z0-9]', '', pattern).lower()
                    if clean_pattern and clean_pattern in collapsed:
                        logger.critical("prompt_injection_detected", 
                                        pattern=pattern, 
                                        form_detected=collapsed[:50],
                                        tenant_id=str(tenant_id))
                        return "[REDACTED]"
            
            # Layer 4: Advanced Adversarial Arbiter
            trigger_keywords = ["prompt", "ignore", "system", "mode", "unfilter", "jailbreak", "dan", "output"]
            if any(kw in forms[0] for kw in trigger_keywords):
                arbiter = AdversarialArbiter()
                if await arbiter.is_adversarial(data):
                    logger.critical("prompt_injection_blocked_by_arbiter", tenant_id=str(tenant_id))
                    return "[REDACTED]"

            return data
        
        elif isinstance(data, list):
            return [await cls.sanitize_input(item, db, tenant_id) for item in data]
        elif isinstance(data, dict):
            return {await cls.sanitize_input(k, db, tenant_id): await cls.sanitize_input(v, db, tenant_id) for k, v in data.items()}
        
        return data
    
    @classmethod
    def validate_output(cls, raw_content: str, schema_class: Type[T]) -> T:
        """
        Parses LLM output and validates it against a Pydantic schema.
        """
        try:
            content = cls._strip_markdown(raw_content)
            data = json.loads(content)
            return schema_class(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("llm_validation_failed", error=str(e), schema=schema_class.__name__)
            raise ValueError(f"LLM output failed validation for {schema_class.__name__}: {str(e)}") from e

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Removes markdown code block wrappers."""
        pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
        match = re.match(pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

class FinOpsRecommendation(BaseModel):
    """Sub-schema for specific recommendations."""
    action: str
    resource: str
    resource_type: str = Field(alias="type") # Map 'type' from JSON to 'resource_type'
    estimated_savings: str
    priority: str
    effort: str
    confidence: str
    autonomous_ready: bool = False

class FinOpsAnalysisResult(BaseModel):
    """Schema for cost analysis results."""
    insights: List[str] = Field(default_factory=list)
    recommendations: List[FinOpsRecommendation] = Field(default_factory=list)
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    forecast: Dict[str, Any] = Field(default_factory=dict)

class ZombieResourceInsight(BaseModel):
    """Schema for individual zombie resource analysis."""
    resource_id: str
    resource_type: str
    provider: str
    explanation: str
    confidence: str
    confidence_score: float
    confidence_reason: str
    recommended_action: str
    monthly_cost: str
    risk_if_deleted: str
    risk_explanation: str
    owner: Optional[str] = "unknown"
    is_gpu: bool = False

class ZombieAnalysisResult(BaseModel):
    """Schema for overall zombie analysis results."""
    summary: str
    total_monthly_savings: str
    resources: List[ZombieResourceInsight] = Field(default_factory=list)
    general_recommendations: List[str] = Field(default_factory=list)

class AdversarialArbiter:
    """
    High-fidelity secondary verification of prompts using heuristics 
    and (if necessary) a small, specialized LLM model.
    """
    async def is_adversarial(self, text: str) -> bool:
        if not text:
            return False
            
        def _to_plain_ascii(s: str) -> str:
            src_sc = "\u1d00\u0299\u1d04\u1d05\u1d07\ua730\u0262\u029c\u026a\u1d0a\u1d0b\u029f\u1d0d\u0274\u1d0f\u1d18\ua7af\u0280\ua731\u1d1b\u1d1c\u1d20\u1d21\u1d22\u028f\u1d22"
            dst_sc = "abcdefghijklmnopqrstuvwxyz"
            s = s.translate(str.maketrans(src_sc, dst_sc))
            s = unicodedata.normalize('NFKC', s).lower()
            homoglyph_map = {
                '\u0430': 'a', '\u0432': 'v', '\u0433': 'g', '\u0434': 'd', '\u0435': 'e',
                '\u0437': 'z', '\u0456': 'i', '\u0458': 'j', '\u043a': 'k', '\u04cf': 'i',
                '\u043c': 'm', '\u043d': 'n', '\u043f': 'p', '\u043e': 'o', '\u0440': 'p',
                '\u0441': 's', '\u0442': 't', '\u0443': 'y', '\u0445': 'x', '\u0446': 'c',
                '\u0447': 'c', '\u0448': 's', '\u0449': 's', '\u044b': 'y', '\u044c': 'b',
                '\u044d': 'e', '\u044e': 'a', '\u044f': 'i', '\u0438': 'i'
            }
            return "".join(homoglyph_map.get(c, c) for c in s)

        processed_text = _to_plain_ascii(text)
        jailbreak_keywords = ["dan", "jailbreak", "unfiltered", "developer mode", "ignore previous", "system prompt", "output only"]
        collapsed = re.sub(r'[^a-z]', '', processed_text)
        for kw in jailbreak_keywords:
            clean_kw = re.sub(r'[^a-z]', '', kw)
            if clean_kw in collapsed:
                return True
            
        return False

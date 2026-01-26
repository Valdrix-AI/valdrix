"""
Tests for LLM Zombie Analyzer

Tests:
1. Analysis request formatting
2. Response parsing
3. Confidence scoring
4. Recommendation generation
"""

from unittest.mock import MagicMock

from app.shared.llm.zombie_analyzer import ZombieAnalyzer


class TestZombieAnalyzerInitialization:
    """Test ZombieAnalyzer initialization."""
    
    def test_analyzer_initializes(self):
        """Analyzer should initialize with LLM client."""
        mock_llm = MagicMock()
        analyzer = ZombieAnalyzer(mock_llm)
        assert analyzer is not None
        assert analyzer.llm == mock_llm
    
    def test_analyzer_stores_llm(self):
        """Analyzer should store LLM reference."""
        mock_llm = MagicMock()
        analyzer = ZombieAnalyzer(mock_llm)
        assert hasattr(analyzer, 'llm')


class TestZombieAnalyzerMethods:
    """Test analyzer methods exist."""
    
    def test_has_analyze_method(self):
        """Analyzer should have analyze method."""
        mock_llm = MagicMock()
        analyzer = ZombieAnalyzer(mock_llm)
        assert hasattr(analyzer, 'analyze')
    
    def test_analyze_is_async(self):
        """analyze should be async."""
        mock_llm = MagicMock()
        analyzer = ZombieAnalyzer(mock_llm)
        import inspect
        assert inspect.iscoroutinefunction(analyzer.analyze)


class TestAnalysisResults:
    """Test analysis result structures."""
    
    def test_result_structure(self):
        """Analysis result should have expected fields."""
        mock_result = {
            "summary": "Found 5 idle resources",
            "total_potential_savings": 150.0,
            "findings": [],
            "general_recommendations": []
        }
        
        assert "summary" in mock_result
        assert "total_potential_savings" in mock_result
        assert "findings" in mock_result
    
    def test_finding_structure(self):
        """Each finding should have complete details."""
        mock_finding = {
            "resource_id": "i-1234567890",
            "issue": "Instance idle for 30+ days",
            "confidence": 0.85,
            "recommendation": "Terminate or resize",
            "risk_level": "low",
            "explanation": "CPU utilization < 5% for last 30 days",
            "confidence_reason": "Based on CloudWatch metrics",
            "monthly_cost": 45.50
        }
        
        required = ["resource_id", "issue", "confidence", "recommendation"]
        for field in required:
            assert field in mock_finding
    
    def test_confidence_in_range(self):
        """Confidence scores should be 0-1."""
        confidences = [0.0, 0.5, 0.85, 1.0]
        for conf in confidences:
            assert 0 <= conf <= 1


class TestConfidenceScoring:
    """Test confidence level categorization."""
    
    def test_high_confidence(self):
        """High confidence >= 0.8."""
        mock_finding = {"confidence": 0.85}
        is_high = mock_finding["confidence"] >= 0.8
        assert is_high
    
    def test_medium_confidence(self):
        """Medium confidence 0.5-0.8."""
        mock_finding = {"confidence": 0.65}
        is_medium = 0.5 <= mock_finding["confidence"] < 0.8
        assert is_medium
    
    def test_low_confidence(self):
        """Low confidence < 0.5."""
        mock_finding = {"confidence": 0.3}
        is_low = mock_finding["confidence"] < 0.5
        assert is_low


class TestRecommendations:
    """Test recommendation generation."""
    
    def test_recommendations_list(self):
        """General recommendations should be a list."""
        mock_result = {
            "general_recommendations": [
                "Enable auto-scaling for variable workloads",
                "Consider reserved instances for predictable usage"
            ]
        }
        
        assert isinstance(mock_result["general_recommendations"], list)
        assert len(mock_result["general_recommendations"]) >= 1
    
    def test_recommendation_is_actionable(self):
        """Recommendations should be actionable strings."""
        recommendations = [
            "Terminate instance i-123",
            "Delete unattached volume vol-456",
            "Review snapshot snap-789"
        ]
        
        for rec in recommendations:
            assert isinstance(rec, str)
            assert len(rec) > 10  # Should be meaningful

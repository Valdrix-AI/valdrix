from unittest.mock import MagicMock, patch
from app.shared.core.tracing import setup_tracing, set_correlation_id, get_current_trace_id

class TestTracingDeep:
    def test_setup_tracing_skipped_in_test(self):
        with patch("app.shared.core.tracing.get_settings") as mock_settings:
            mock_settings.return_value.TESTING = True
            setup_tracing()
            # Should just return

    def test_setup_tracing_console(self):
        with patch("app.shared.core.tracing.get_settings") as mock_settings:
            mock_settings.return_value.TESTING = False
            mock_settings.return_value.OTEL_EXPORTER_OTLP_ENDPOINT = None
            
            # Patch classes within the tracing module namespace
            with patch("app.shared.core.tracing.TracerProvider") as mock_provider:
                with patch("app.shared.core.tracing.BatchSpanProcessor") as mock_processor:
                    with patch("app.shared.core.tracing.ConsoleSpanExporter") as mock_exporter:
                        setup_tracing()
                        assert mock_provider.called
                        assert mock_processor.called
                        assert mock_exporter.called

    def test_setup_tracing_otlp(self):
        with patch("app.shared.core.tracing.get_settings") as mock_settings:
            mock_settings.return_value.TESTING = False
            mock_settings.return_value.OTEL_EXPORTER_OTLP_ENDPOINT = "http://jaeger:4317"
            mock_settings.return_value.OTEL_EXPORTER_OTLP_INSECURE = True
            
            with patch("app.shared.core.tracing.OTLPSpanExporter") as mock_exporter:
                with patch("app.shared.core.tracing.TracerProvider") as mock_provider:
                    setup_tracing()
                    assert mock_exporter.called
                    assert mock_provider.called

    def test_setup_tracing_fastapi(self):
        mock_app = MagicMock()
        with patch("app.shared.core.tracing.get_settings") as mock_settings:
            mock_settings.return_value.TESTING = False
            mock_settings.return_value.OTEL_EXPORTER_OTLP_ENDPOINT = None
            
            with patch("app.shared.core.tracing.FastAPIInstrumentor") as mock_instrumentor:
                setup_tracing(app=mock_app)
                assert mock_instrumentor.instrument_app.called

    def test_set_correlation_id(self):
        mock_span = MagicMock()
        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            set_correlation_id("test-corr-id")
            mock_span.set_attribute.assert_called_with("correlation_id", "test-corr-id")

    def test_get_current_trace_id_valid(self):
        mock_span = MagicMock()
        mock_span.get_span_context.return_value.is_valid = True
        mock_span.get_span_context.return_value.trace_id = 0x1234567890abcdef1234567890abcdef
        
        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            tid = get_current_trace_id()
            assert tid == "1234567890abcdef1234567890abcdef"

    def test_get_current_trace_id_invalid(self):
        mock_span = MagicMock()
        mock_span.get_span_context.return_value.is_valid = False
        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            assert get_current_trace_id() is None

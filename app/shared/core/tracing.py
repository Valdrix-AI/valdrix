import os
import structlog
from opentelemetry import trace
from opentelemetry.trace import Tracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi import FastAPI
from app.shared.core.config import get_settings

logger = structlog.get_logger()


def setup_tracing(app: FastAPI | None = None) -> None:
    """
    Sets up OpenTelemetry tracing for the application.
    """
    settings = get_settings()

    if settings.TESTING:
        logger.info("setup_tracing_skipped_in_test")
        return

    # 1. Define Resource
    resource = Resource(
        attributes={
            ResourceAttributes.SERVICE_NAME: "valdrix-api",
            "env": os.getenv("ENV", "development"),
        }
    )

    # 2. Setup Provider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # 3. Add Exporter (OTLP if endpoint provided, otherwise Console)
    otlp_endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if otlp_endpoint:
        insecure = settings.OTEL_EXPORTER_OTLP_INSECURE
        logger.info("setup_tracing_otlp", endpoint=otlp_endpoint, insecure=insecure)
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    else:
        logger.info("setup_tracing_console")
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # 4. Instrument FastAPI if provided
    if app:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi_instrumented")


def get_tracer(name: str) -> Tracer:
    """Returns a tracer instance for manual instrumentation."""
    return trace.get_tracer(name)


def set_correlation_id(correlation_id: str) -> None:
    """Sets a correlation ID for the current span."""
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute("correlation_id", correlation_id)


def get_current_trace_id() -> str | None:
    """
    Returns the current trace ID in hex format.
    Used for correlating logs and Sentry events.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return None

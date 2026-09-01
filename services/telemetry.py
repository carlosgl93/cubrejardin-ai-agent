"""OpenTelemetry instrumentation for tracing and metrics."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional
from functools import wraps

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.trace import Status, StatusCode
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter  # Fallback for dev

from config import get_settings
from utils import logger


# ─── Telemetry Configuration ────────────────────────────────────────────────────

class TelemetryConfig:
    """Configuration for OpenTelemetry."""

    def __init__(self) -> None:
        settings = get_settings()

        self.service_name = settings.app_name
        self.service_version = "1.0.0"
        self.environment = settings.environment

        # OTLP endpoint (Cloud Trace / Cloud Monitoring)
        self.otlp_endpoint = getattr(settings, 'otel_endpoint', None)

        # Enable console exporter for development
        self.use_console_exporter = settings.environment == "development"

        # Sample rate (1.0 = 100%, 0.1 = 10%)
        self.sample_rate = float(getattr(settings, 'otel_sample_rate', 1.0))


# ─── Telemetry Manager ────────────────────────────────────────────────────────

class TelemetryManager:
    """Manages OpenTelemetry tracing and metrics."""

    _instance: Optional[TelemetryManager] = None

    def __init__(self, config: Optional[TelemetryConfig] = None) -> None:
        self.config = config or TelemetryConfig()
        self._tracer: Optional[trace.Tracer] = None
        self._meter: Optional[metrics.Meter] = None
        self._initialized = False

        # Metrics
        self._messages_received: Optional[metrics.Counter] = None
        self._messages_sent: Optional[metrics.Counter] = None
        self._agent_latency: Optional[metrics.Histogram] = None
        self._rag_confidence: Optional[metrics.Histogram] = None
        self._error_count: Optional[metrics.Counter] = None

    @classmethod
    def get_instance(cls) -> TelemetryManager:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self) -> None:
        """Initialize OpenTelemetry with configured exporters."""
        if self._initialized:
            return

        # Create resource with service info
        resource = Resource.create({
            SERVICE_NAME: self.config.service_name,
            SERVICE_VERSION: self.config.service_version,
            "deployment.environment": self.config.environment,
        })

        # Setup tracing
        self._setup_tracing(resource)

        # Setup metrics
        self._setup_metrics(resource)

        self._initialized = True
        logger.info(
            "telemetry_initialized",
            extra={
                "service": self.config.service_name,
                "environment": self.config.environment,
                "otlp_endpoint": self.config.otlp_endpoint,
            }
        )

    def _setup_tracing(self, resource: Resource) -> None:
        """Configure tracing provider and exporters."""
        # Choose exporter
        if self.config.otlp_endpoint:
            try:
                exporter = OTLPSpanExporter(endpoint=self.config.otlp_endpoint)
            except Exception:
                logger.warning("Failed to create OTLP exporter, using console")
                exporter = ConsoleSpanExporter()
        elif self.config.use_console_exporter:
            exporter = ConsoleSpanExporter()
        else:
            # No exporter configured
            return

        # Create provider with sampler
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        sampler = TraceIdRatioBased(self.config.sample_rate)

        provider = TracerProvider(resource=resource, sampler=sampler)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(
            self.config.service_name,
            self.config.service_version
        )

    def _setup_metrics(self, resource: Resource) -> None:
        """Configure metrics provider and exporters."""
        if self.config.otlp_endpoint:
            try:
                metric_exporter = OTLPMetricExporter(endpoint=self.config.otlp_endpoint)
                reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60000)
            except Exception:
                reader = None
        else:
            reader = None

        provider = MeterProvider(resource=resource, metric_readers=[reader] if reader else [])
        metrics.set_meter_provider(provider)

        self._meter = metrics.get_meter(self.config.service_name, self.config.service_version)

        # Create metrics instruments
        self._messages_received = self._meter.create_counter(
            name="whatsapp.messages.received",
            description="Total messages received",
            unit="1"
        )

        self._messages_sent = self._meter.create_counter(
            name="whatsapp.messages.sent",
            description="Total messages sent",
            unit="1"
        )

        self._agent_latency = self._meter.create_histogram(
            name="whatsapp.agent.latency",
            description="Agent processing latency in seconds",
            unit="s"
        )

        self._rag_confidence = self._meter.create_histogram(
            name="whatsapp.rag.confidence",
            description="RAG confidence scores",
            unit="1"
        )

        self._error_count = self._meter.create_counter(
            name="whatsapp.errors",
            description="Error count by type",
            unit="1"
        )

    def get_tracer(self) -> trace.Tracer:
        """Get the configured tracer."""
        if not self._initialized:
            self.initialize()
        return self._tracer or trace.get_tracer(self.config.service_name)

    # ─── Metric Recording Methods ──────────────────────────────────────────────

    def record_message_received(self, channel: str, tenant_id: Optional[str] = None) -> None:
        """Record an inbound message."""
        if self._messages_received:
            attributes = {
                "channel": channel,
                "tenant_id": tenant_id or "unknown"
            }
            self._messages_received.add(1, attributes)

    def record_message_sent(self, channel: str, message_type: str = "text") -> None:
        """Record an outbound message."""
        if self._messages_sent:
            self._messages_sent.add(1, {"channel": channel, "type": message_type})

    def record_agent_latency(self, agent_name: str, latency_seconds: float, success: bool = True) -> None:
        """Record agent processing latency."""
        if self._agent_latency:
            self._agent_latency.record(
                latency_seconds,
                {
                    "agent": agent_name,
                    "success": str(success)
                }
            )

    def record_rag_confidence(self, confidence: float, category: Optional[str] = None) -> None:
        """Record RAG confidence score."""
        if self._rag_confidence:
            self._rag_confidence.record(
                confidence,
                {"category": category or "unknown"}
            )

    def record_error(self, error_type: str, context: Optional[str] = None) -> None:
        """Record an error occurrence."""
        if self._error_count:
            self._error_count.add(1, {"type": error_type, "context": context or "general"})


# ─── Tracing Decorators ───────────────────────────────────────────────────────

def traced(
    span_name: str,
    attributes: Optional[dict] = None
) -> Callable:
    """Decorator to add tracing to a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = TelemetryManager.get_instance().get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    start = time.perf_counter()
                    result = await func(*args, **kwargs)
                    latency = time.perf_counter() - start
                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute("latency_seconds", latency)
                    return result

                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = TelemetryManager.get_instance().get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    start = time.perf_counter()
                    result = func(*args, **kwargs)
                    latency = time.perf_counter() - start
                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute("latency_seconds", latency)
                    return result

                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@asynccontextmanager
async def traced_span(
    name: str,
    attributes: Optional[dict] = None
):
    """Context manager for creating a traced span."""
    tracer = TelemetryManager.get_instance().get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


# ─── FastAPI Instrumentation Setup ─────────────────────────────────────────────

def setup_fastapi_instrumentation(app) -> None:
    """Setup OpenTelemetry for FastAPI application."""
    TelemetryManager.get_instance().initialize()

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Instrument HTTPX (used by WhatsApp service)
    HTTPXClientInstrumentor().instrument()


# ─── Convenience Functions ─────────────────────────────────────────────────────

def get_telemetry() -> TelemetryManager:
    """Get telemetry manager instance."""
    return TelemetryManager.get_instance()


# ─── Span Attributes Constants ─────────────────────────────────────────────────

class SpanAttributes:
    """Standard span attribute names."""

    # Message attributes
    MESSAGE_ID = "whatsapp.message.id"
    MESSAGE_TYPE = "whatsapp.message.type"
    CHANNEL = "whatsapp.channel"
    RECIPIENT = "whatsapp.recipient"
    TENANT_ID = "whatsapp.tenant_id"

    # Agent attributes
    AGENT_NAME = "agent.name"
    AGENT_CATEGORY = "agent.category"
    AGENT_CONFIDENCE = "agent.confidence"
    AGENT_LATENCY = "agent.latency_seconds"

    # RAG attributes
    RAG_SOURCES = "rag.sources"
    RAG_CONFIDENCE = "rag.confidence"
    RAG_RETRIEVAL_TIME = "rag.retrieval_time_seconds"

    # Error attributes
    ERROR_TYPE = "error.type"
    ERROR_MESSAGE = "error.message"

"""Optional OpenTelemetry instrumentation for the hello-api service."""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_observability(app: FastAPI) -> bool:
    """Enable OTLP export only when an endpoint is explicitly configured."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False

    service_name = os.getenv("OTEL_SERVICE_NAME", "hello-api").strip() or "hello-api"
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "kaviont",
            "deployment.environment.name": os.getenv("KAVIONT_ENV", "local"),
        }
    )

    traces = TracerProvider(resource=resource)
    traces.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=endpoint,
                insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true",
            )
        )
    )
    trace.set_tracer_provider(traces)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=endpoint,
            insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true",
        ),
        export_interval_millis=5000,
    )
    metrics.set_meter_provider(
        MeterProvider(resource=resource, metric_readers=[metric_reader])
    )

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=traces,
        meter_provider=metrics.get_meter_provider(),
        excluded_urls="/healthz,/readyz",
    )
    return True

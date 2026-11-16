"""Optional OpenTelemetry instrumentation for the hello-api service."""

from __future__ import annotations

import os

import psutil
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import Observation
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
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"

    traces = TracerProvider(resource=resource)
    traces.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
    )
    trace.set_tracer_provider(traces)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=insecure),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Process gauges make resource pressure visible without mounting the Docker socket.
    process = psutil.Process(os.getpid())
    meter = meter_provider.get_meter("kaviont.hello-api")

    def observe_cpu(_options):
        cpu_count = max(psutil.cpu_count(logical=True) or 1, 1)
        utilization = process.cpu_percent(interval=None) / (100.0 * cpu_count)
        yield Observation(utilization, {"process.name": service_name})

    def observe_memory(_options):
        resident_bytes = process.memory_info().rss
        yield Observation(resident_bytes, {"process.name": service_name})

    meter.create_observable_gauge(
        "process.cpu.usage",
        callbacks=[observe_cpu],
        unit="1",
        description="Process CPU utilization normalized across logical CPUs",
    )
    meter.create_observable_gauge(
        "process.memory.usage",
        callbacks=[observe_memory],
        unit="By",
        description="Resident memory used by the hello-api process",
    )

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=traces,
        meter_provider=meter_provider,
        excluded_urls="/healthz,/readyz",
    )
    return True

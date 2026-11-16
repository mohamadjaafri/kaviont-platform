"""Optional OpenTelemetry instrumentation for Kaviont API and worker processes."""

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


def _configure_providers(service_name: str):
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return None, None

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

    process = psutil.Process(os.getpid())
    meter = meter_provider.get_meter(f"kaviont.{service_name.replace('-', '_')}")

    def observe_cpu(_options):
        cpu_count = max(psutil.cpu_count(logical=True) or 1, 1)
        utilization = process.cpu_percent(interval=None) / (100.0 * cpu_count)
        yield Observation(utilization, {"process.name": service_name})

    def observe_memory(_options):
        yield Observation(
            process.memory_info().rss,
            {"process.name": service_name},
        )

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
        description="Resident memory used by the process",
    )
    return traces, meter_provider


def configure_observability(app: FastAPI) -> bool:
    """Enable OTLP export and FastAPI instrumentation when configured."""
    traces, meter_provider = _configure_providers(
        os.getenv("OTEL_SERVICE_NAME", "hello-api").strip() or "hello-api"
    )
    if traces is None or meter_provider is None:
        return False

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=traces,
        meter_provider=meter_provider,
        excluded_urls="/healthz,/readyz",
    )
    return True


def configure_worker_observability() -> bool:
    """Enable process and client-request telemetry for the standalone worker."""
    traces, meter_provider = _configure_providers(
        os.getenv("OTEL_SERVICE_NAME", "market-data-worker").strip()
        or "market-data-worker"
    )
    return traces is not None and meter_provider is not None

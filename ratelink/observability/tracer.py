from contextlib import contextmanager
from typing import Any, Iterator, Optional, Protocol

class Tracer(Protocol):
    @contextmanager
    def span(
        self,
        name: str,
        **attributes: Any
    ) -> Iterator[None]:
        """
        Create a tracing span.
        
        Args:
            name: Span name
            **attributes: Span attributes
        
        Yields:
            None
        """
        ...


class NoOpTracer:
    @contextmanager
    def span(
        self,
        name: str,
        **attributes: Any
    ) -> Iterator[None]:
        """Create a no-op span."""
        yield


try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class OpenTelemetryTracer:
    def __init__(
        self,
        service_name: str = "rate-limiter",
        tracer_provider: Optional[Any] = None
    ):
        if not OTEL_AVAILABLE:
            raise ImportError(
                "opentelemetry-api is required for OpenTelemetryTracer. "
                "Install with: pip install opentelemetry-api opentelemetry-sdk"
            )
        
        if tracer_provider:
            self._tracer = tracer_provider.get_tracer(service_name)
        else:
            self._tracer = trace.get_tracer(service_name)
    
    @contextmanager
    def span(
        self,
        name: str,
        **attributes: Any
    ) -> Iterator[None]:
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
            try:
                yield
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(e)
                raise


class RateLimiterTracer:
    def __init__(self, tracer: Optional[Tracer] = None):
        self._tracer = tracer or NoOpTracer()
    
    @contextmanager
    def trace_check(
        self,
        key: str,
        algorithm: str,
        backend: str,
        weight: int = 1
    ) -> Iterator[None]:
        with self._tracer.span(
            "rate_limit.check",
            key=key,
            algorithm=algorithm,
            backend=backend,
            weight=weight
        ):
            yield
    
    @contextmanager
    def trace_backend_operation(
        self,
        backend: str,
        operation: str,
        key: Optional[str] = None
    ) -> Iterator[None]:
        attrs = {
            "backend": backend,
            "operation": operation,
        }
        if key:
            attrs["key"] = key
        
        with self._tracer.span(
            f"rate_limit.backend.{operation}",
            **attrs
        ):
            yield
    
    @contextmanager
    def trace_algorithm(
        self,
        algorithm: str,
        key: str
    ) -> Iterator[None]:
        with self._tracer.span(
            f"rate_limit.algorithm.{algorithm}",
            algorithm=algorithm,
            key=key
        ):
            yield


def create_tracer(
    enabled: bool = True,
    service_name: str = "rate-limiter",
    tracer_provider: Optional[Any] = None
) -> Tracer:
    if not enabled:
        return NoOpTracer()
    
    if not OTEL_AVAILABLE:
        import warnings
        warnings.warn(
            "OpenTelemetry not available. Install with: "
            "pip install opentelemetry-api opentelemetry-sdk"
        )
        return NoOpTracer()
    
    return OpenTelemetryTracer(
        service_name=service_name,
        tracer_provider=tracer_provider
    )
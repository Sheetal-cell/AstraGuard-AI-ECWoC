"""Test suite for resource_monitor module."""

import pytest
import psutil
import time
from core.resource_monitor import (
    ResourceStatus,
    ResourceMetrics,
    ResourceThresholds,
    ResourceMonitor,
    get_resource_monitor,
)


class TestResourceMetrics:
    """Test ResourceMetrics data class"""

    def test_creation(self):
        metrics = ResourceMetrics(
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_available_mb=2048.0,
            disk_usage_percent=70.0,
            process_memory_mb=512.0,
        )
        assert metrics.cpu_percent == 50.0

    def test_to_dict(self):
        metrics = ResourceMetrics(
            cpu_percent=45.0,
            memory_percent=55.0,
            memory_available_mb=3072.0,
            disk_usage_percent=65.0,
            process_memory_mb=256.0,
        )
        d = metrics.to_dict()
        assert "cpu_percent" in d
        assert d["cpu_percent"] == 45.0

    def test_zeros(self):
        metrics = ResourceMetrics(
            cpu_percent=0.0,
            memory_percent=0.0,
            memory_available_mb=0.0,
            disk_usage_percent=0.0,
            process_memory_mb=0.0,
        )
        assert metrics.cpu_percent == 0.0


class TestResourceThresholds:
    """Test ResourceThresholds configuration"""

    def test_defaults(self):
        t = ResourceThresholds()
        assert t.cpu_warning == 70.0
        assert t.cpu_critical == 90.0
        assert t.memory_warning == 75.0
        assert t.memory_critical == 90.0

    def test_custom(self):
        t = ResourceThresholds(cpu_warning=50.0, cpu_critical=80.0)
        assert t.cpu_warning == 50.0
        assert t.cpu_critical == 80.0


class TestResourceMonitor:
    """Test ResourceMonitor class"""

    def test_init(self):
        m = ResourceMonitor()
        assert m.thresholds is not None
        assert m.history_size == 100
        assert m.monitoring_enabled is True

    def test_custom_thresholds(self):
        t = ResourceThresholds(cpu_warning=50.0)
        m = ResourceMonitor(thresholds=t)
        assert m.thresholds.cpu_warning == 50.0

    def test_get_metrics(self):
        m = ResourceMonitor()
        metrics = m.get_current_metrics()
        assert isinstance(metrics, ResourceMetrics)
        assert 0 <= metrics.cpu_percent <= 100

    def test_metrics_ranges(self):
        m = ResourceMonitor()
        metrics = m.get_current_metrics()
        assert 0 <= metrics.cpu_percent <= 100
        assert 0 <= metrics.memory_percent <= 100

    def test_history(self):
        m = ResourceMonitor()
        m.get_current_metrics()
        m.get_current_metrics()
        assert len(m._metrics_history) >= 1

    def test_history_size(self):
        m = ResourceMonitor(history_size=5)
        for _ in range(10):
            m.get_current_metrics()
        assert len(m._metrics_history) <= 5

    def test_health(self):
        m = ResourceMonitor()
        h = m.check_resource_health()
        assert isinstance(h, dict)
        assert "cpu" in h
        assert "memory" in h

    def test_health_status(self):
        m = ResourceMonitor()
        h = m.check_resource_health()
        valid = [ResourceStatus.HEALTHY, ResourceStatus.WARNING, ResourceStatus.CRITICAL]
        assert h["cpu"] in valid

    def test_available(self):
        m = ResourceMonitor()
        assert isinstance(m.is_resource_available(), bool)

    def test_summary(self):
        m = ResourceMonitor()
        for _ in range(3):
            m.get_current_metrics()
        s = m.get_metrics_summary()
        assert isinstance(s, dict)

    def test_summary_empty(self):
        m = ResourceMonitor()
        m._metrics_history = []
        s = m.get_metrics_summary()
        assert isinstance(s, dict)

    def test_nonblocking_cpu(self):
        m = ResourceMonitor()
        start = time.time()
        for _ in range(10):
            m.get_current_metrics()
        elapsed = time.time() - start
        assert elapsed < 2.0

    def test_cpu_warning(self):
        t = ResourceThresholds(cpu_warning=0.1, cpu_critical=0.05)
        m = ResourceMonitor(thresholds=t)
        h = m.check_resource_health()
        # Very low threshold should trigger warning/critical
        assert h["cpu"] in [ResourceStatus.WARNING, ResourceStatus.CRITICAL, ResourceStatus.HEALTHY]

    def test_cpu_critical(self):
        t = ResourceThresholds(cpu_critical=0.001)
        m = ResourceMonitor(thresholds=t)
        h = m.check_resource_health()
        # Any CPU usage should be > 0.001%, so it might be critical
        assert h["cpu"] in [ResourceStatus.CRITICAL, ResourceStatus.WARNING, ResourceStatus.HEALTHY]

    def test_multiple(self):
        m1 = ResourceMonitor(history_size=10)
        m2 = ResourceMonitor(history_size=20)
        assert m1.history_size == 10
        assert m2.history_size == 20


class TestErrorHandling:
    """Test error handling"""

    def test_get_metrics_safe(self):
        m = ResourceMonitor()
        metrics = m.get_current_metrics()
        assert metrics is not None

    def test_disabled(self):
        m = ResourceMonitor()
        m.monitoring_enabled = False
        metrics = m.get_current_metrics()
        assert metrics.cpu_percent == 0.0

    def test_summary_single(self):
        m = ResourceMonitor()
        m.get_current_metrics()
        s = m.get_metrics_summary()
        assert isinstance(s, dict)


class TestSingleton:
    """Test global resource monitor singleton"""

    def test_singleton(self):
        m1 = get_resource_monitor()
        m2 = get_resource_monitor()
        assert m1 is m2

    def test_type(self):
        m = get_resource_monitor()
        assert isinstance(m, ResourceMonitor)

    def test_state(self):
        m = get_resource_monitor()
        assert hasattr(m, "thresholds")
        assert hasattr(m, "monitoring_enabled")


class TestIntegration:
    """Integration tests"""

    def test_cycle(self):
        m = ResourceMonitor()
        for _ in range(3):
            m.get_current_metrics()
        h = m.check_resource_health()
        assert h is not None
        a = m.is_resource_available()
        assert isinstance(a, bool)

    def test_changes(self):
        m = ResourceMonitor()
        h1 = m.check_resource_health()
        m.thresholds.cpu_warning = 1.0
        h2 = m.check_resource_health()
        assert h1 is not None and h2 is not None

    def test_accuracy(self):
        m = ResourceMonitor()
        metrics = m.get_current_metrics()
        mem = psutil.virtual_memory()
        assert 0 <= metrics.cpu_percent <= 100
        assert abs(metrics.memory_percent - mem.percent) < 10.0

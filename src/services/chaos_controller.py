"""
Chaos Engineering Fault Injection Controller.
Manages controlled failure scenarios with bounded blast radius and automatic expiration.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import threading

from src.models.chaos import ActiveFault, ChaosInjectionRequest, FaultType
from src.services.topology_graph import topology_engine


class ChaosController:
    def __init__(self):
        self._lock = threading.Lock()
        self._active_faults: Dict[str, ActiveFault] = {}

    def inject_fault(self, request: ChaosInjectionRequest) -> ActiveFault:
        """Injects a failure into a target service with a time-to-live (TTL)."""
        if not topology_engine.is_service_registered(request.service_name):
            raise ValueError(f"Target service '{request.service_name}' is not recognized in topology.")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=request.duration_sec)

        fault = ActiveFault(
            service_name=request.service_name,
            fault_type=request.fault_type,
            magnitude=request.magnitude,
            started_at=now,
            expires_at=expires_at,
            is_active=True,
            injected_by=request.injected_by,
        )

        with self._lock:
            # Service can have multiple fault types, or replace existing of same type
            key = f"{fault.service_name}:{fault.fault_type}"
            self._active_faults[key] = fault

        return fault

    def remove_fault(self, service_name: str, fault_type: Optional[FaultType] = None) -> List[str]:
        """Clears specific or all faults for a service."""
        cleared_ids = []
        with self._lock:
            to_remove = []
            for key, fault in self._active_faults.items():
                if fault.service_name == service_name:
                    if fault_type is None or fault.fault_type == fault_type:
                        fault.is_active = False
                        to_remove.append(key)
                        cleared_ids.append(fault.fault_id)

            for key in to_remove:
                del self._active_faults[key]

        return cleared_ids

    def clear_all_faults(self) -> int:
        """Emergency reset: clears all injected faults across the ecosystem."""
        with self._lock:
            count = len(self._active_faults)
            self._active_faults.clear()
            return count

    def get_active_faults(self, service_name: Optional[str] = None) -> List[ActiveFault]:
        """Returns list of currently active faults, pruning expired faults."""
        now = datetime.now(timezone.utc)
        active: List[ActiveFault] = []

        with self._lock:
            expired_keys = []
            for key, fault in self._active_faults.items():
                if now > fault.expires_at:
                    fault.is_active = False
                    expired_keys.append(key)
                else:
                    if service_name is None or fault.service_name == service_name:
                        active.append(fault)

            for k in expired_keys:
                del self._active_faults[k]

        return active

    def is_fault_active(self, service_name: str, fault_type: FaultType) -> Optional[ActiveFault]:
        """Checks if a particular fault type is currently impacting a service."""
        faults = self.get_active_faults(service_name)
        for f in faults:
            if f.fault_type == fault_type:
                return f
        return None


chaos_controller = ChaosController()

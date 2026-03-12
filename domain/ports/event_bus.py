"""
event_bus.py — Simple Thread-Safe Event Bus (Pub/Sub Mediator)
"""
import threading
from typing import Callable, Any, Dict, List
import queue
import logging

class EventBus:
    """
    A simple thread-safe Event Bus for decoupling components.
    Subscribers can register callbacks for specific event types (strings).
    Publishers can emit events that will be dispatched to all subscribers.
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventBus, cls).__new__(cls)
                cls._instance._subscribers = {} # type: Dict[str, List[Callable]]
                cls._instance._sub_lock = threading.RLock()
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Register a callback for a specific event type."""
        with self._sub_lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Unregister a callback for a specific event type."""
        with self._sub_lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass

    def publish(self, event_type: str, event_data: Any = None) -> None:
        """
        Publish an event to all subscribers.
        Callbacks are executed synchronously in the caller's thread.
        For GUI updates, ensure the callback uses Tkinter's after() or similar.
        """
        with self._sub_lock:
            callbacks = list(self._subscribers.get(event_type, []))
            
        for callback in callbacks:
            try:
                callback(event_data)
            except Exception as e:
                logging.error(f"Error in event subscriber for {event_type}: {e}")

# Global singleton instance for easy import
bus = EventBus()

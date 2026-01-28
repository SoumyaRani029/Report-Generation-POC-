"""
Performance tracking and timing utilities for dashboard.
Tracks execution time of functions and provides real-time logging.
"""
import time
import functools
import threading
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Callable
import json

# Global storage for logs and timings
_logs = deque(maxlen=1000)  # Store last 1000 log messages
_timings = {}  # Store function timings
_log_lock = threading.Lock()
_timing_lock = threading.Lock()

class LogCapture:
    """Capture print statements and redirect to log storage."""
    
    def __init__(self):
        self.original_print = print
        self.enabled = False
        
    def enable(self):
        """Enable log capture."""
        self.enabled = True
        
    def disable(self):
        """Disable log capture."""
        self.enabled = False
        
    def log(self, message: str, level: str = "INFO", silent: bool = False):
        """Add a log message."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "datetime": datetime.now().isoformat()
        }
        
        with _log_lock:
            _logs.append(log_entry)
        
        # Only print to console if not silent (timing messages should be silent)
        if not silent:
            self.original_print(f"[{timestamp}] [{level}] {message}")
        
    def get_logs(self, since: Optional[float] = None) -> List[Dict]:
        """Get logs since a specific timestamp."""
        with _log_lock:
            if since:
                return [log for log in _logs if log.get("datetime") >= since]
            return list(_logs)
        
    def clear_logs(self):
        """Clear all logs."""
        with _log_lock:
            _logs.clear()
    
    def clear_logs_static():
        """Static method to clear logs."""
        with _log_lock:
            _logs.clear()

# Global log capture instance
log_capture = LogCapture()

def track_time(func_name: Optional[str] = None):
    """
    Decorator to track function execution time.
    
    Usage:
        @track_time("extract_text")
        def extract_text(...):
            ...
    """
    def decorator(func: Callable):
        name = func_name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            # Log to dashboard only (silent=True means don't print to terminal)
            log_capture.log(f"⏱️ Starting: {name}", "TIMING", silent=True)
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                with _timing_lock:
                    if name not in _timings:
                        _timings[name] = []
                    _timings[name].append({
                        "duration": elapsed,
                        "timestamp": datetime.now().isoformat(),
                        "success": True
                    })
                
                # Log to dashboard only (silent=True means don't print to terminal)
                log_capture.log(f"✅ Completed: {name} ({elapsed:.2f}s)", "TIMING", silent=True)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                
                with _timing_lock:
                    if name not in _timings:
                        _timings[name] = []
                    _timings[name].append({
                        "duration": elapsed,
                        "timestamp": datetime.now().isoformat(),
                        "success": False,
                        "error": str(e)
                    })
                
                # Error messages should still print to terminal
                log_capture.log(f"❌ Failed: {name} ({elapsed:.2f}s) - {str(e)}", "ERROR", silent=False)
                raise
        
        return wrapper
    return decorator

def get_timings() -> Dict:
    """Get all function timings."""
    with _timing_lock:
        result = {}
        for func_name, times in _timings.items():
            if times:
                durations = [t["duration"] for t in times if t.get("success")]
                if durations:
                    result[func_name] = {
                        "count": len(durations),
                        "total": sum(durations),
                        "average": sum(durations) / len(durations),
                        "min": min(durations),
                        "max": max(durations),
                        "last": times[-1]
                    }
        return result

def clear_timings():
    """Clear all timing data."""
    with _timing_lock:
        _timings.clear()

def get_recent_logs(count: int = 100) -> List[Dict]:
    """Get recent log entries."""
    with _log_lock:
        return list(_logs)[-count:]


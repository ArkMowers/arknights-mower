from dataclasses import dataclass
from typing import Optional


@dataclass
class DebugInfo:
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    source_code: Optional[str] = None
    exception_message: Optional[str] = None
    timestamp: Optional[str] = None

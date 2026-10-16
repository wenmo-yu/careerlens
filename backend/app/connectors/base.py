from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConnectorItem:
    external_id: str
    source_name: str
    content: str
    metadata: dict[str, Any]

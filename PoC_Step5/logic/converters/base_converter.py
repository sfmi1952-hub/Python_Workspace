from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class ConversionResult:
    markdown_text: str
    page_count: int
    conversion_time_sec: float
    source_path: str
    method_name: str
    errors: List[str] = field(default_factory=list)


class BaseConverter(ABC):
    @abstractmethod
    def convert(self, file_path: str) -> ConversionResult:
        ...

    @abstractmethod
    def name(self) -> str:
        ...

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

class BaseConverter(ABC):
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def convert_request(self, data: dict, target_format: str) -> dict:
        """Convert request to target format"""
        pass
    
    @abstractmethod
    def convert_response(self, data: dict, source_format: str) -> dict:
        """Convert response from source format"""
        pass
    
    @abstractmethod
    def convert_stream_chunk(self, chunk: str, source_format: str) -> str:
        """Convert streaming chunk from source format"""
        pass

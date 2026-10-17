import abc
from typing import List, Tuple
from app.ingestion.models import ParsedSymbol, ParsedRelationship

class BaseParser(abc.ABC):
    @abc.abstractmethod
    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        pass

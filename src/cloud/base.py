from abc import ABC, abstractmethod
from typing import Optional


class CloudProvider(ABC):

    @abstractmethod
    def upload(self, local_path: str, filename: str) -> Optional[str]:
        """Upload un fichier. Retourne l'URL publique ou None en cas d'échec."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Vérifie si le provider est joignable."""
        pass

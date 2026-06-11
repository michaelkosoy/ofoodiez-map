from abc import ABC, abstractmethod

class BaseApprovalHandler(ABC):
    """
    Abstract Base Class for saving approved event details
    to their respective database models.
    """
    
    @abstractmethod
    def save(self, app, data: dict) -> bool:
        """
        Save the approved event data to the database.
        Must run within the Flask app context.
        """
        pass

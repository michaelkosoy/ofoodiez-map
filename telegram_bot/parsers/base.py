from abc import ABC, abstractmethod

class BaseEventParser(ABC):
    """
    Abstract Base Class for parsing events (like Pop-ups or Happy Hours)
    from text or flyer images using Google Gemini AI.
    """
    
    @abstractmethod
    def get_prompt(self) -> str:
        """Return the prompt template instructing Gemini how to parse the details."""
        pass

    @abstractmethod
    def parse_text(self, text: str) -> dict:
        """Parse structured details from plain unformatted text."""
        pass

    @abstractmethod
    def parse_image(self, image_bytes: bytes, mime_type: str) -> dict:
        """Parse structured details from image flyer bytes."""
        pass

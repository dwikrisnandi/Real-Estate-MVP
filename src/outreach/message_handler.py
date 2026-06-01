"""
Message Handler
===============
Loads, parses, and personalizes message templates from a text file.
Supports placeholders like {username}, {display_name}, etc.
"""

from loguru import logger
from pathlib import Path
from typing import Optional



class MessageHandler:
    """
    Manages message templates with dynamic placeholder substitution.

    Template files support these placeholders:
      {username}      — The recipient's username
      {display_name}  — The recipient's display name (falls back to username)
    """

    def __init__(self, template_path: str | Path):
        self._path = Path(template_path)
        self._template: str = ""
        self._load_template()

    def _load_template(self) -> None:
        """Load the message template from disk."""
        if not self._path.exists():
            raise FileNotFoundError(
                f"Message template not found: {self._path}\n"
                f"Create a text file with your message at this path."
            )

        self._template = self._path.read_text(encoding="utf-8").strip()

        if not self._template:
            raise ValueError(f"Message template is empty: {self._path}")

        # Count placeholders for logging
        placeholder_count = self._template.count("{")
        logger.info(
            "Loaded message template from %s (%d chars, ~%d placeholders)",
            self._path.name,
            len(self._template),
            placeholder_count,
        )

    def personalize(
        self,
        username: str,
        display_name: Optional[str] = None,
        **extra_fields,
    ) -> str:
        """
        Generate a personalized message for a specific user.

        Args:
            username:     The recipient's username.
            display_name: Optional display name (defaults to username).
            **extra_fields: Additional template variables.

        Returns:
            The personalized message string.
        """
        fields = {
            "username": username,
            "display_name": display_name or username,
            **extra_fields,
        }

        try:
            message = self._template.format(**fields)
        except KeyError as e:
            logger.warning(
                "Unknown placeholder %s in template — using raw template", e
            )
            message = self._template
        except Exception as e:
            logger.error("Template rendering error: %s", e)
            message = self._template

        return message

    def reload(self) -> None:
        """Hot-reload the template from disk (useful during development)."""
        self._load_template()
        logger.info("Template reloaded from %s", self._path.name)

    @property
    def template(self) -> str:
        """Return the raw template string."""
        return self._template

    def preview(self, username: str = "example_user") -> str:
        """Generate a preview message for testing."""
        return self.personalize(username=username, display_name="Example User")

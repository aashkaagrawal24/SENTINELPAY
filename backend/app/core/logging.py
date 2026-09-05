import logging
import re

SECRET_PATTERN = re.compile(r"(?i)(secret|api[_-]?key|token|password)=([^\s,]+)")


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return SECRET_PATTERN.sub(r"\1=[REDACTED]", super().format(record))


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().handlers = [handler]

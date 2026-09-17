import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.core.storage import STORAGE_DIRECTORIES

logger = logging.getLogger(__name__)


def clean_up_conversation_files(
    storage_root: Path,
    *,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    for directory in STORAGE_DIRECTORIES:
        user_directory = (storage_root / directory / str(user_id)).resolve()
        conversation_directory = (user_directory / str(conversation_id)).resolve()

        if conversation_directory.parent != user_directory:
            raise ValueError("Conversation storage path escaped its user directory")

        try:
            shutil.rmtree(conversation_directory)
        except FileNotFoundError:
            continue
        except OSError:
            logger.exception(
                "Failed to remove conversation storage directory path=%s",
                conversation_directory,
            )

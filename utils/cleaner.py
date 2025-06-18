import os
import shutil
from loguru import logger

def remove_temp_files(paths: list[str]) -> None:
    """
    Удаляет временные файлы и директории, если они существуют.
    """
    for path in paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
                logger.info(f"🧹 Удалён файл: {path}")
            elif os.path.isdir(path):
                shutil.rmtree(path)
                logger.info(f"🧹 Удалена директория: {path}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить {path}: {e}")

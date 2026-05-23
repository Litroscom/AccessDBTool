import logging
import os
import sys
import constants

def setup_logging(base_dir):
    log_file = os.path.join(base_dir or constants._BASE_DIR, os.path.basename(constants.LOG_FILE))
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    # Sotto pythonw.exe (lanciato da VBS) sys.stderr è None:
    # StreamHandler() crasherebbe al primo log.write()
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    logger = logging.getLogger("AccessDBTool")
    logger.info("Sistema di logging inizializzato.")
    return logger

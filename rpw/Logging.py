import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import Settings

loggers = Settings.Logs['loggers']


class Logger:
    @staticmethod
    def setup_logger(logger_name, logger) -> logging.Logger:
        if not Path(Settings.Main['log_path']).exists():
            os.makedirs(Settings.Main['log_path'])
        logger.setLevel(loggers[logger_name]['log_level'])
        file_handler = RotatingFileHandler(loggers[logger_name]['log_file'],
                                           maxBytes=10_000_000, backupCount=5, mode='a')
        file_handler.setFormatter(loggers[logger_name]['log_formatter'])
        file_handler.setLevel(loggers[logger_name]['log_level'])
        logger.addHandler(file_handler)
        logger.setLevel(loggers[logger_name]['log_level'])

        return logger

    @staticmethod
    def timestamp():
        return f"{datetime.now()}"

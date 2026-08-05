import logging
from logging.handlers import QueueHandler
from multiprocessing import Queue

import pytest

from app.detectors.process_recording import close_birdnet_session_loggers


def test_completed_birdnet_session_queues_are_closed() -> None:
    logger_name = "birdnet.session_rc1-resource-test"
    logger = logging.getLogger(logger_name)
    queue = Queue()
    logger.addHandler(QueueHandler(queue))

    close_birdnet_session_loggers()

    assert logger_name not in logging.Logger.manager.loggerDict
    with pytest.raises(ValueError, match="closed"):
        queue.put("unused")

import logging

from voiceos import db
from voiceos.worker.outbox import run_forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_forever(db.configure())

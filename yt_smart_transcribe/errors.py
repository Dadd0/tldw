"""StageError and the exit code for each pipeline stage."""

CONFIG, FEED, DOWNLOAD, TRANSCRIPTION, DATABASE = 2, 3, 4, 5, 6


class StageError(Exception):
    def __init__(self, code: int, stage: str, message: str):
        super().__init__(message)
        self.code, self.stage = code, stage

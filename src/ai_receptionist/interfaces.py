from collections.abc import Iterator, Sequence
from typing import Protocol

import numpy as np


class AudioInput(Protocol):
    def utterances(self) -> Iterator[np.ndarray]: ...


class SpeechRecognizer(Protocol):
    def transcribe(self, audio: str | np.ndarray) -> str: ...

    def transcribe_partial(self, audio: np.ndarray) -> str: ...


class Responder(Protocol):
    def respond(
        self,
        text: str,
        history: Sequence[dict[str, str]] = (),
        business_context: str = "",
    ) -> str: ...


class EndOfTurnDetector(Protocol):
    def completion_probability(self, audio: np.ndarray) -> float: ...


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str) -> tuple[np.ndarray, int]: ...

    def close(self) -> None: ...

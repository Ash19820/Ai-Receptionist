from collections.abc import Iterator
import logging
import time

import numpy as np
import sounddevice as sd

from ai_receptionist.config import Settings

logger = logging.getLogger(__name__)


class EnergyTurnDetector:
    """Small dependency-free endpoint detector; replaceable by Silero VAD later."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def utterances(self) -> Iterator[np.ndarray]:
        frame_samples = int(self.settings.sample_rate * self.settings.frame_ms / 1000)
        silence_frames_to_end = max(
            1, int(self.settings.end_silence_seconds * 1000 / self.settings.frame_ms)
        )
        max_frames = max(
            1, int(self.settings.max_utterance_seconds * 1000 / self.settings.frame_ms)
        )
        active = False
        silence_frames = 0
        frames: list[np.ndarray] = []

        logger.info("Listening; speak after the prompt.")
        try:
            with sd.InputStream(
                samplerate=self.settings.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=frame_samples,
            ) as stream:
                while True:
                    frame, overflowed = stream.read(frame_samples)
                    if overflowed:
                        logger.warning("Microphone input overflow; audio frame may be incomplete.")
                    mono = np.asarray(frame[:, 0], dtype=np.float32).copy()
                    rms = float(np.sqrt(np.mean(np.square(mono))))
                    speech = rms >= self.settings.speech_threshold

                    if speech:
                        if not active:
                            active = True
                            logger.info("Speech detected.")
                        silence_frames = 0
                    elif active:
                        silence_frames += 1

                    if active:
                        frames.append(mono)

                    if active and (silence_frames >= silence_frames_to_end or len(frames) >= max_frames):
                        utterance = np.concatenate(frames)
                        yield utterance
                        # Drop audio buffered while ASR/LLM/TTS ran. This also prevents
                        # the assistant's own speaker output from becoming the next turn.
                        stream.abort()
                        stream.start()
                        active = False
                        silence_frames = 0
                        frames = []
                        logger.info("Listening for the next turn.")
        except sd.PortAudioError as exc:
            raise RuntimeError(
                "Microphone is unavailable. Check that the device is connected and permitted, "
                "then choose the correct input device in your system audio settings."
            ) from exc


def play_audio(audio: np.ndarray, sample_rate: int) -> None:
    try:
        sd.play(audio, sample_rate, blocking=True)
    except sd.PortAudioError as exc:
        raise RuntimeError(
            "Speaker output is unavailable. Check the output device and system audio permissions."
        ) from exc

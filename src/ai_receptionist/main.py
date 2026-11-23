import logging
import math
import resource
import time

from ai_receptionist.audio import EnergyTurnDetector, play_audio
from ai_receptionist.config import Settings
from ai_receptionist.providers import LocalKokoro, LocalLlamaResponder, LocalWhisper


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_environment()

    # Load all models before activating the microphone so setup failures are immediate.
    print("Loading speech models from local files.")
    asr = LocalWhisper(settings)
    responder = LocalLlamaResponder(settings)
    tts = LocalKokoro(settings)
    detector = EnergyTurnDetector(settings)

    print("Local receptionist ready. Speak after the listening prompt; press Ctrl+C to quit.")
    first_audio_latencies: list[float] = []
    stage_timings: list[dict[str, float]] = []
    try:
        for audio in detector.utterances():
            started = time.perf_counter()
            try:
                stage_started = time.perf_counter()
                transcript = asr.transcribe(audio)
                asr_seconds = time.perf_counter() - stage_started
                if not transcript:
                    print("I didn't catch that. Please try again.")
                    continue
                print(f"You: {transcript}")
                stage_started = time.perf_counter()
                answer = responder.respond(transcript)
                llm_seconds = time.perf_counter() - stage_started
                print(f"Assistant: {answer}")
                stage_started = time.perf_counter()
                spoken, sample_rate = tts.synthesize(answer)
                tts_seconds = time.perf_counter() - stage_started
                first_audio_seconds = time.perf_counter() - started
                play_audio(spoken, sample_rate)
                first_audio_latencies.append(first_audio_seconds)
                stage_timings.append(
                    {"asr": asr_seconds, "llm": llm_seconds, "tts": tts_seconds}
                )
                elapsed = time.perf_counter() - started
                print(
                    f"[Turn: first audio {first_audio_seconds:.2f}s; "
                    f"ASR {asr_seconds:.2f}s; LLM {llm_seconds:.2f}s; "
                    f"TTS {tts_seconds:.2f}s; full turn {elapsed:.2f}s]"
                )
            except TimeoutError as exc:
                print(f"Assistant: {exc}")
            except Exception as exc:
                logging.exception("Turn failed")
                print(f"Assistant: Sorry, I hit a local processing problem: {exc}")
    except KeyboardInterrupt:
        print("\nGoodbye.")
    finally:
        tts.close()
        if first_audio_latencies:
            values = sorted(first_audio_latencies)
            p50 = values[math.ceil(0.50 * len(values)) - 1]
            p95 = values[math.ceil(0.95 * len(values)) - 1]
            print(
                f"\nSession summary ({len(values)} completed turns): "
                f"first-audio p50={p50:.2f}s, p95={p95:.2f}s"
            )
            print(
                "Stage averages: "
                + ", ".join(
                    f"{name}={sum(item[name] for item in stage_timings) / len(stage_timings):.2f}s"
                    for name in ("asr", "llm", "tts")
                )
            )
        usage = resource.getrusage(resource.RUSAGE_SELF)
        print(
            f"Process usage: CPU {usage.ru_utime + usage.ru_stime:.1f}s; "
            f"peak resident memory {usage.ru_maxrss / 1024:.0f} MiB"
        )


if __name__ == "__main__":
    main()

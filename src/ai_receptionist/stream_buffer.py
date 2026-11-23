"""Small bounded buffers for the browser's PCM16 WebSocket stream."""


def append_pcm16_bounded(buffer: bytearray, chunk: bytes, limit_bytes: int) -> bool:
    """Append an even-byte PCM16 chunk up to ``limit_bytes``.

    Returns true once the buffer is full or the chunk had to be truncated.
    The caller can use this to end an overlong turn without letting a client
    grow memory use indefinitely.
    """
    if limit_bytes <= 0 or limit_bytes % 2:
        raise ValueError("PCM16 buffer limit must be a positive even number")
    if len(chunk) % 2:
        raise ValueError("PCM16 chunks must contain complete 16-bit samples")

    available = max(0, limit_bytes - len(buffer))
    accepted = min(available, len(chunk))
    accepted -= accepted % 2
    buffer.extend(chunk[:accepted])
    return len(buffer) >= limit_bytes or accepted < len(chunk)

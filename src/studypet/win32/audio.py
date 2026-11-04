"""Win32 PlaySoundW 메모리 비동기 재생 및 PCM 볼륨 스케일링 (DEVELOPMENT_PLAN.md 4-14)."""
from __future__ import annotations

import array
import ctypes
from pathlib import Path

from studypet.win32.api import SND_ASYNC, SND_MEMORY, SND_NODEFAULT, winmm


def scale_wav(raw: bytes, volume: float) -> bytes:
    """44바이트 표준 16-bit PCM WAV 헤더를 유지하고 샘플 진폭을 volume(0.0~1.0)으로 스케일링한다."""
    v = max(0.0, min(1.0, float(volume)))
    if len(raw) <= 44 or abs(v - 1.0) < 1e-6:
        return raw
    header = raw[:44]
    body = raw[44:]
    # 2바이트 정렬 보장
    trim_len = len(body) - (len(body) % 2)
    samples = array.array("h")
    samples.frombytes(body[:trim_len])
    for i in range(len(samples)):
        val = int(samples[i] * v)
        if val > 32767:
            val = 32767
        elif val < -32768:
            val = -32768
        samples[i] = val
    return header + samples.tobytes()


class SoundPlayer:
    def __init__(self, wav_paths: dict[str, Path] | None = None, volume: float = 0.7, enabled: bool = True) -> None:
        self.enabled: bool = enabled
        self.volume: float = max(0.0, min(1.0, float(volume)))
        self._raw: dict[str, bytes] = {}
        self._buffers: dict[str, ctypes.Array[ctypes.c_char]] = {}
        self._playing: ctypes.Array[ctypes.c_char] | None = None

        if wav_paths:
            for k, p in wav_paths.items():
                if p.exists():
                    self._raw[k] = p.read_bytes()
        self.set_volume(self.volume)

    def load_raw_bytes(self, key: str, wav_bytes: bytes) -> None:
        self._raw[key] = wav_bytes
        self._buffers[key] = ctypes.create_string_buffer(scale_wav(wav_bytes, self.volume))

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.stop()

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, float(v)))
        winmm.PlaySoundW(None, None, 0)
        self._buffers = {
            k: ctypes.create_string_buffer(scale_wav(raw, self.volume))
            for k, raw in self._raw.items()
        }

    def play(self, key: str) -> bool:
        if not self.enabled or self.volume <= 0.0:
            return False
        buf = self._buffers.get(key)
        if buf is None:
            return False
        self._playing = buf  # 비동기 재생 중 GC 방지
        ok = winmm.PlaySoundW(
            ctypes.cast(buf, ctypes.c_void_p),
            None,
            SND_MEMORY | SND_ASYNC | SND_NODEFAULT,
        )
        return bool(ok)

    def stop(self) -> None:
        winmm.PlaySoundW(None, None, 0)
        self._playing = None


"""8-bit 레트로 칩튠 효과음 4종(start, phase, celebrate, afk) 생성기 (DEVELOPMENT_PLAN.md 4-14)."""
from __future__ import annotations

import math
from pathlib import Path
import random
import struct
import wave


ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RATE = 22050
MAX_AMP = int(32767 * 0.45)  # 진폭 0.5 상한 준수

# 음계 주파수 (Hz)
NOTE_C5 = 523.25
NOTE_E5 = 659.25
NOTE_G5 = 783.99
NOTE_C6 = 1046.50


def synth_tone(
    freq: float,
    duration_ms: int,
    wave_type: str = "square",
    rng: random.Random | None = None,
) -> bytes:
    n_samples = int(SAMPLE_RATE * duration_ms / 1000.0)
    fade_samples = min(n_samples // 6, int(SAMPLE_RATE * 0.01))
    out = bytearray()
    r = rng or random.Random(42)

    for i in range(n_samples):
        if freq <= 0.0:
            val = 0.0
        elif wave_type == "square":
            phase = (i * freq / SAMPLE_RATE) % 1.0
            val = 1.0 if phase < 0.5 else -1.0
        elif wave_type == "triangle":
            phase = (i * freq / SAMPLE_RATE) % 1.0
            val = 4.0 * abs(phase - 0.5) - 1.0
        elif wave_type == "sparkle":
            phase = (i * freq / SAMPLE_RATE) % 1.0
            sq = 1.0 if phase < 0.5 else -1.0
            noise = r.uniform(-0.4, 0.4)
            val = max(-1.0, min(1.0, sq * 0.7 + noise))
        else:
            val = math.sin(2.0 * math.pi * freq * i / SAMPLE_RATE)

        # 클릭 노이즈 방지용 짧은 엔벨로프
        env = 1.0
        if fade_samples > 0:
            if i < fade_samples:
                env = i / fade_samples
            elif i >= n_samples - fade_samples:
                env = (n_samples - 1 - i) / fade_samples

        sample_int = int(max(-32767, min(32767, val * MAX_AMP * env)))
        out.extend(struct.pack("<h", sample_int))
    return bytes(out)


def synth_glide_triangle(f_start: float, f_end: float, duration_ms: int) -> bytes:
    n_samples = int(SAMPLE_RATE * duration_ms / 1000.0)
    fade_samples = min(n_samples // 6, int(SAMPLE_RATE * 0.015))
    out = bytearray()
    phase = 0.0
    for i in range(n_samples):
        t = i / max(1, n_samples - 1)
        freq = f_start + (f_end - f_start) * t
        phase = (phase + freq / SAMPLE_RATE) % 1.0
        val = 4.0 * abs(phase - 0.5) - 1.0
        env = 1.0
        if fade_samples > 0 and i >= n_samples - fade_samples:
            env = (n_samples - 1 - i) / fade_samples
        sample_int = int(val * MAX_AMP * env)
        out.extend(struct.pack("<h", sample_int))
    return bytes(out)


def write_wav(path: Path, pcm_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)


def main() -> int:
    sfx_dir = ROOT / "assets" / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261103)

    # 1. start.wav: 구형파 C5 -> E5 -> G5 (각 80ms)
    pcm_start = (
        synth_tone(NOTE_C5, 80, "square")
        + synth_tone(NOTE_E5, 80, "square")
        + synth_tone(NOTE_G5, 80, "square")
    )
    write_wav(sfx_dir / "start.wav", pcm_start)

    # 2. phase.wav: 구형파 G5 120ms, 쉼 60ms, G5 120ms
    pcm_phase = (
        synth_tone(NOTE_G5, 120, "square")
        + synth_tone(0.0, 60, "square")
        + synth_tone(NOTE_G5, 120, "square")
    )
    write_wav(sfx_dir / "phase.wav", pcm_phase)

    # 3. celebrate.wav: C5 E5 G5 C6 아르페지오(각 90ms) + 노이즈 반짝임 200ms
    pcm_celeb = (
        synth_tone(NOTE_C5, 90, "square")
        + synth_tone(NOTE_E5, 90, "square")
        + synth_tone(NOTE_G5, 90, "square")
        + synth_tone(NOTE_C6, 90, "square")
        + synth_tone(NOTE_C6, 200, "sparkle", rng=rng)
    )
    write_wav(sfx_dir / "celebrate.wav", pcm_celeb)

    # 4. afk.wav: 삼각파 E5 -> C5 하강 300ms
    pcm_afk = synth_glide_triangle(NOTE_E5, NOTE_C5, 300)
    write_wav(sfx_dir / "afk.wav", pcm_afk)

    print(f"[gen_sfx] 효과음 4종 생성 완료: {sfx_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""A quiet sine tone and explicit technical labels; no human speech or corpus claim."""

import array
import json
import math
import sys
import wave


def audio_fixture(folder):
    audio = folder / 'technical-tone.wav'
    samples = array.array(
        'h', (int(2000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(48000))
    )
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(audio), 'wb') as target:
        target.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        target.writeframes(samples.tobytes())
    annotation = folder / 'segments.json'
    rows = [
        {
            'time_start': 0.2,
            'time_end': 0.7,
            'text_ba': 'TECHNICAL AUDIO FIXTURE - NOT BASHKIR',
            'translation': 'Техническая аудиофикстура, не речь.',
            'lang_pair': 'ba-ru',
        }
    ]
    annotation.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return audio, annotation, rows

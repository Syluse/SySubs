import logging
import string
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Tuple

logger = logging.getLogger("sysubs")

@dataclass
class SubtitleBlock:
    index: int
    start: float
    end: float
    lines: List[str]

    def to_srt(self) -> str:
        start_str = _format_srt_time(self.start)
        end_str = _format_srt_time(self.end)
        content = "\n".join(self.lines)
        return f"{self.index}\n{start_str} --> {end_str}\n{content}\n"

def _format_srt_time(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def _flatten_words(word_segments) -> List[Tuple[str, float, float]]:
    words = []
    for segment in word_segments:
        if hasattr(segment, 'words') and segment.words:
            source = segment.words
        elif isinstance(segment, dict) and 'words' in segment:
            source = segment['words']
        elif hasattr(segment, 'word'):
            source = [segment]
        else:
            continue

        for w in source:
            if hasattr(w, 'start'):
                w_start, w_end, w_word = w.start, w.end, w.word
            else:
                w_start, w_end, w_word = w['start'], w['end'], w['word']
            if w_start is not None and w_end is not None:
                words.append((w_word.strip(), w_start, w_end))
    return words

def _group_words_mode(words, value, long_word_threshold, max_gap):
    blocks = []
    current = []

    def emit():
        if current:
            blocks.append(SubtitleBlock(
                index=len(blocks) + 1,
                start=current[0][1],
                end=current[-1][2],
                lines=[" ".join(w[0] for w in current)]
            ))
            current.clear()

    for w in words:
        word_text = w[0]
        if len(word_text) > long_word_threshold:
            emit()
            current.append(w)
            emit()
        else:
            if current and w[1] - current[-1][2] >= max_gap:
                emit()
            current.append(w)
            if len(current) >= value:
                emit()

    emit()
    return blocks

def _group_chars_mode(words, value, max_lines, long_word_threshold, max_gap):
    blocks = []
    current = []
    cur_lines = [[]]
    cur_line_len = 0

    def emit():
        nonlocal cur_line_len
        if current:
            lines = [" ".join(line) for line in cur_lines]
            blocks.append(SubtitleBlock(
                index=len(blocks) + 1,
                start=current[0][1],
                end=current[-1][2],
                lines=lines
            ))
            current.clear()
            cur_lines.clear()
            cur_lines.append([])
            cur_line_len = 0

    for w in words:
        word_text = w[0]
        if len(word_text) > long_word_threshold:
            emit()
            current.append(w)
            cur_lines[0].append(word_text)
            cur_line_len = len(word_text)
            emit()
            continue

        if current and w[1] - current[-1][2] >= max_gap:
            emit()

        would_fit = cur_line_len + 1 + len(word_text) <= value if cur_lines[-1] else True

        if not would_fit:
            if len(cur_lines) >= max_lines:
                emit()
            else:
                cur_lines.append([])
                cur_line_len = 0

        was_empty = len(cur_lines[-1]) == 0
        cur_line_len += (0 if was_empty else 1) + len(word_text)
        cur_lines[-1].append(word_text)
        current.append(w)

    emit()
    return blocks

def _clamp_overlaps(blocks):
    for i in range(len(blocks) - 1):
        if blocks[i].end > blocks[i+1].start:
            blocks[i].end = blocks[i+1].start - 0.001
    return blocks

def _apply_text_formatting(words, text_transform, strip_punctuation):
    if not strip_punctuation and text_transform == "none":
        return words

    result = []
    for word_text, start, end in words:
        text = word_text
        if strip_punctuation:
            text = text.strip(string.punctuation)
        if text_transform == "upper":
            text = text.upper()
        elif text_transform == "lower":
            text = text.lower()
        if text:
            result.append((text, start, end))
    return result

def format_srt(word_segments: List, preset_config: dict) -> str:
    if not word_segments:
        return ""

    all_words = _flatten_words(word_segments)
    if not all_words:
        return ""

    all_words = _apply_text_formatting(
        all_words,
        text_transform=preset_config.get("text_transform", "none"),
        strip_punctuation=preset_config.get("strip_punctuation", False),
    )
    if not all_words:
        return ""

    mode = preset_config.get("mode", "words")
    value = preset_config.get("value", 2)
    max_lines = preset_config.get("max_lines", 1)
    long_word_threshold = preset_config.get("long_word_threshold", 10)
    max_gap = preset_config.get("max_gap", 0.5)

    if mode == "words":
        blocks = _group_words_mode(all_words, value, long_word_threshold, max_gap)
    else:
        blocks = _group_chars_mode(all_words, value, max_lines, long_word_threshold, max_gap)

    _clamp_overlaps(blocks)
    return "\n".join(b.to_srt() for b in blocks)

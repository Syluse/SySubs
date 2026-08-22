import logging
import string
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Tuple, Iterable
from constants import MIN_GAP_SECONDS, Preset

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
    millis = round(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def _flatten_words(word_segments) -> List[Tuple[str, float, float, str]]:
    """Flattens segments into (word, start, end, language) tuples.

    The parent segment's `language` is carried down to every word so the
    block builder can split on language boundaries (code-switched speech).
    """
    words = []
    for segment in word_segments:
        if hasattr(segment, 'words') and segment.words:
            source = segment.words
            lang = getattr(segment, 'language', None)
        elif isinstance(segment, dict) and 'words' in segment:
            source = segment['words']
            lang = segment.get('language')
        elif hasattr(segment, 'word'):
            source = [segment]
            lang = getattr(segment, 'language', None)
        else:
            continue

        for w in source:
            if hasattr(w, 'start'):
                w_start, w_end, w_word = w.start, w.end, w.word
            else:
                w_start, w_end, w_word = w['start'], w['end'], w['word']
            if w_start is not None and w_end is not None:
                words.append((w_word.strip(), w_start, w_end, lang))
    return words

class _BlockBuilder:
    """Accumulates words into blocks and flushes them as SubtitleBlocks.

    Keeps block/line state in one place so the long-word path cannot drift
    out of sync with the normal fill path. Tracks the current language and
    flushes the block on a language change, so code-switched speech splits
    at the language boundary rather than by gap alone.
    """

    def __init__(self, show_language_tags: bool = False):
        self.show_language_tags = show_language_tags
        self.current: List[Tuple[str, float, float, str]] = []
        self.lines: List[List[str]] = [[]]
        self.line_len = 0
        self.blocks: List[SubtitleBlock] = []
        self.current_language = None

    def flush(self) -> None:
        """Emits the accumulated block (if any) and resets all state."""
        if not self.current:
            return
        lines = [" ".join(line) for line in self.lines]
        if self.show_language_tags and self.current_language:
            lines[0] = f"[{self.current_language}] {lines[0]}"
        self.blocks.append(SubtitleBlock(
            index=len(self.blocks) + 1,
            start=self.current[0][1],
            end=self.current[-1][2],
            lines=lines
        ))
        self.current.clear()
        self.lines = [[]]
        self.line_len = 0
        self.current_language = None

    def add_word(self, w: Tuple[str, float, float, str]) -> None:
        """Appends a word to the current block's last line."""
        word_text, start, end, lang = w
        if self.current_language is not None and lang != self.current_language:
            self.flush()
        self.current_language = lang
        self.current.append(w)
        if self.lines[-1]:
            self.line_len += 1 + len(word_text)
        else:
            self.line_len = len(word_text)
        self.lines[-1].append(word_text)

    def start_line(self) -> None:
        """Starts a new line within the current block."""
        self.lines.append([])
        self.line_len = 0

def _clamp_max_gap(max_gap) -> float:
    """Clamps so a 0/negative gap never splits on every word pair."""
    return max(max_gap, MIN_GAP_SECONDS)

def _group_words_mode(words, value, long_word_threshold, max_gap, show_language_tags=False):
    builder = _BlockBuilder(show_language_tags=show_language_tags)
    max_gap = _clamp_max_gap(max_gap)

    for w in words:
        word_text = w[0]
        if len(word_text) > long_word_threshold:
            builder.flush()
            builder.add_word(w)
            builder.flush()
            continue

        if builder.current and w[1] - builder.current[-1][2] >= max_gap:
            builder.flush()

        builder.add_word(w)
        if len(builder.current) >= value:
            builder.flush()

    builder.flush()
    return builder.blocks

def _group_chars_mode(words, value, max_lines, long_word_threshold, max_gap, show_language_tags=False):
    builder = _BlockBuilder(show_language_tags=show_language_tags)
    max_gap = _clamp_max_gap(max_gap)

    for w in words:
        word_text = w[0]
        if len(word_text) > long_word_threshold:
            builder.flush()
            builder.add_word(w)
            builder.flush()
            continue

        if builder.current and w[1] - builder.current[-1][2] >= max_gap:
            builder.flush()

        if builder.lines[-1]:
            would_fit = builder.line_len + 1 + len(word_text) <= value
        else:
            would_fit = True

        if not would_fit:
            if len(builder.lines) >= max_lines:
                builder.flush()
            else:
                builder.start_line()

        builder.add_word(w)

    builder.flush()
    return builder.blocks

def _clamp_overlaps(blocks):
    for i in range(len(blocks) - 1):
        if blocks[i].end > blocks[i+1].start:
            blocks[i].end = blocks[i+1].start - 0.001
    return blocks

def _apply_text_formatting(words, text_transform, strip_punctuation):
    if not strip_punctuation and text_transform == "none":
        return words

    result = []
    for word_text, start, end, lang in words:
        text = word_text
        if strip_punctuation:
            text = text.strip(string.punctuation)
        if text_transform == "upper":
            text = text.upper()
        elif text_transform == "lower":
            text = text.lower()
        if text:
            result.append((text, start, end, lang))
    return result

def format_srt(word_segments: Iterable, preset_config) -> str:
    if not word_segments:
        return ""

    if isinstance(preset_config, dict):
        pc = Preset()
        pc.mode = preset_config.get("mode", "words")
        pc.value = preset_config.get("value", 2)
        pc.max_lines = preset_config.get("max_lines", 1)
        pc.long_word_threshold = preset_config.get("long_word_threshold", 10)
        pc.max_gap = preset_config.get("max_gap", 0.05)
        pc.text_transform = preset_config.get("text_transform", "none")
        pc.strip_punctuation = preset_config.get("strip_punctuation", False)
        pc.show_language_tags = preset_config.get("show_language_tags", False)
        preset_config = pc

    all_words = _flatten_words(word_segments)
    if not all_words:
        return ""

    all_words = _apply_text_formatting(
        all_words,
        text_transform=preset_config.text_transform,
        strip_punctuation=preset_config.strip_punctuation,
    )
    if not all_words:
        return ""

    mode = preset_config.mode
    value = preset_config.value
    max_lines = preset_config.max_lines
    long_word_threshold = preset_config.long_word_threshold
    max_gap = preset_config.max_gap
    show_language_tags = preset_config.show_language_tags

    if mode == "words":
        blocks = _group_words_mode(all_words, value, long_word_threshold, max_gap, show_language_tags)
    else:
        blocks = _group_chars_mode(all_words, value, max_lines, long_word_threshold, max_gap, show_language_tags)

    _clamp_overlaps(blocks)
    return "\n".join(b.to_srt() for b in blocks)

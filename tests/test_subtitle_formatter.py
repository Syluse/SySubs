"""Tests for services/subtitle_formatter.py — pure logic, no mocks needed."""

import pytest

from services.subtitle_formatter import (
    SubtitleBlock,
    _format_srt_time,
    format_srt,
)


class FakeWord:
    def __init__(self, word, start, end):
        self.word = word
        self.start = start
        self.end = end


class FakeSegment:
    def __init__(self, language, words):
        self.language = language
        self.words = [FakeWord(w, s, e) for w, s, e in words]


# ---------------------------------------------------------------- SRT times

def test_format_srt_time_zero():
    assert _format_srt_time(0) == "00:00:00,000"


def test_format_srt_time_millis():
    assert _format_srt_time(1.5) == "00:00:01,500"


def test_format_srt_time_minutes():
    assert _format_srt_time(62.5) == "00:01:02,500"


def test_format_srt_time_hours():
    assert _format_srt_time(3661.25) == "01:01:01,250"


# ---------------------------------------------------------------- empty input

def test_format_srt_empty_segments():
    assert format_srt([], {}) == ""


def test_format_srt_segments_without_words():
    assert format_srt([FakeSegment("en", [])], {}) == ""


# ---------------------------------------------------------------- words mode

def test_words_mode_groups_by_value():
    segs = [FakeSegment("en", [
        ("a", 0.0, 0.1), ("b", 0.1, 0.2), ("c", 0.2, 0.3),
        ("d", 0.3, 0.4), ("e", 0.4, 0.5),
    ])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 3
    assert "a b" in blocks[0]
    assert "c d" in blocks[1]
    assert "e" in blocks[2]


def test_words_mode_gap_splits():
    segs = [FakeSegment("en", [
        ("a", 0.0, 0.1), ("b", 0.1, 0.2), ("c", 1.5, 1.6),
    ])]
    cfg = {"mode": "words", "value": 10, "max_gap": 0.5}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 2
    assert "a b" in blocks[0]
    assert "c" in blocks[1]


def test_words_mode_zero_max_gap_is_clamped():
    # max_gap=0 must not split every word pair (clamped to 0.01s)
    segs = [FakeSegment("en", [
        ("a", 0.0, 0.1), ("b", 0.1, 0.2), ("c", 0.2, 0.3),
    ])]
    cfg = {"mode": "words", "value": 3, "max_gap": 0}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 1


def test_long_word_gets_its_own_block():
    long_word = "Supercalifragilisticexpialidocious"
    segs = [FakeSegment("en", [
        ("a", 0.0, 0.1), (long_word, 0.2, 0.6), ("b", 0.7, 0.8),
    ])]
    cfg = {"mode": "words", "value": 10, "max_gap": 10.0, "long_word_threshold": 10}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 3
    assert long_word in blocks[1]
    assert "a" in blocks[0]
    assert "b" in blocks[2]


# ---------------------------------------------------------------- chars mode

def test_chars_mode_wraps_to_new_line():
    segs = [FakeSegment("en", [
        ("aaa", 0.0, 0.1), ("bb", 0.1, 0.2), ("cc", 0.2, 0.3),
    ])]
    # "aaa bb" = 6 chars fits; "cc" would overflow onto line 2
    cfg = {"mode": "chars", "value": 6, "max_lines": 2, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 1
    assert "aaa bb\ncc" in blocks[0]


def test_chars_mode_flushes_when_lines_exhausted():
    segs = [FakeSegment("en", [
        ("aaaaaa", 0.0, 0.1), ("bbbbbb", 0.1, 0.2), ("cccccc", 0.2, 0.3),
    ])]
    # each word is 6 chars; value=6 max_lines=1 -> every word its own block
    cfg = {"mode": "chars", "value": 6, "max_lines": 1, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 3


# ---------------------------------------------------------------- formatting

def test_strip_punctuation():
    segs = [FakeSegment("en", [
        ("Hello,", 0.0, 0.2), ("world!", 0.2, 0.4),
    ])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "strip_punctuation": True}
    out = format_srt(segs, cfg)
    assert "Hello world" in out
    assert "Hello," not in out
    assert "world!" not in out


def test_strip_punctuation_drops_empty_words():
    segs = [FakeSegment("en", [
        ("!!!", 0.0, 0.2), ("ok", 0.2, 0.4),
    ])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "strip_punctuation": True}
    out = format_srt(segs, cfg)
    assert "ok" in out
    assert "!!!" not in out


def test_text_transform_upper():
    segs = [FakeSegment("en", [("hello", 0.0, 0.2)])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "text_transform": "upper"}
    out = format_srt(segs, cfg)
    assert "HELLO" in out


def test_text_transform_lower():
    segs = [FakeSegment("en", [("HELLO", 0.0, 0.2)])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "text_transform": "lower"}
    out = format_srt(segs, cfg)
    assert "hello" in out


# ---------------------------------------------------------------- overlaps

def test_overlaps_are_clamped():
    segs = [FakeSegment("en", [
        ("a", 0.0, 2.0), ("b", 2.5, 3.0),
    ])]
    cfg = {"mode": "words", "value": 1, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    lines = [l for l in out.splitlines() if "-->" in l]
    assert len(lines) == 2
    first_end = lines[0].split("-->")[1].strip().split()[0]
    second_start = lines[1].split("-->")[0].strip().split()[0]
    assert first_end <= second_start


def test_subtitle_block_srt_output():
    block = SubtitleBlock(index=3, start=1.0, end=2.5, lines=["Hello", "world"])
    assert block.to_srt() == "3\n00:00:01,000 --> 00:00:02,500\nHello\nworld\n"


# ---------------------------------------------------------------- language

def test_language_boundary_flushes_block():
    segs = [
        FakeSegment("en", [("Hello", 0.0, 0.3), ("world", 0.3, 0.6)]),
        FakeSegment("fil", [("Kamusta", 0.6, 0.9), ("ka", 0.9, 1.2)]),
    ]
    cfg = {"mode": "words", "value": 10, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 2
    assert "Hello world" in blocks[0]
    assert "Kamusta ka" in blocks[1]


def test_language_tags_when_enabled():
    segs = [FakeSegment("en", [("Hello", 0.0, 0.3)])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "show_language_tags": True}
    out = format_srt(segs, cfg)
    assert "[en] Hello" in out


def test_no_language_tags_by_default():
    segs = [FakeSegment("en", [("Hello", 0.0, 0.3)])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    assert "[en]" not in out


def test_none_language_does_not_split():
    segs = [FakeSegment(None, [("a", 0.0, 0.3), ("b", 0.3, 0.6)])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    blocks = [b for b in out.split("\n\n") if b]
    assert len(blocks) == 1
    assert "a b" in blocks[0]


def test_language_tags_skipped_when_language_unknown():
    segs = [FakeSegment(None, [("Hello", 0.0, 0.3)])]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "show_language_tags": True}
    out = format_srt(segs, cfg)
    assert "Hello" in out
    assert "[None]" not in out


# ---------------------------------------------------------------- segment shapes

def test_dict_segments_supported():
    segs = [{
        "language": "ja",
        "words": [
            {"word": "konnichiwa", "start": 0.0, "end": 0.4},
            {"word": "sekai", "start": 0.4, "end": 0.8},
        ],
    }]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0, "show_language_tags": True}
    out = format_srt(segs, cfg)
    assert "[ja] konnichiwa sekai" in out


def test_flat_word_segments_supported():
    segs = [FakeWord("solo", 0.0, 0.5)]
    cfg = {"mode": "words", "value": 2, "max_gap": 10.0}
    out = format_srt(segs, cfg)
    assert "solo" in out

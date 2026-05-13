# SySubs

Speech-to-text subtitle generator originally made for me to use in editing, and to learn in building apps. 
SySubs transcribes audio from video and audio files into a `.srt` subtitle using local speech-to-text models.

## Features

- **Offline transcription:** no internet needed aside from downloading the models, runs locally on your machine
- **Model selection:** choose from tiny (fast) to large-v3 (accurate) based on your hardware
- **Language support:** Mainly English, somewhat supports other languages
- **Subtitle presets:** Short-form / Reels, Landscape / YouTube, or Custom formatting
- **Text formatting:** uppercase/lowercase transform, punctuation stripping
- **GPU acceleration:** Only when your hardware supports it
- **Portable:** extract and run, no installation required

## Limitations

- Accuracy depends on audio quality, background noise, and clarity of speech
- Larger models (medium, large-v3) require significant RAM/VRAM and may be slow on older hardware
- Model downloads are large (75MB for tiny, up to 3GB for large-v3)
- Mainly optimized for English; other languages have varying accuracy
- Windows only

## Quick Start

1. Download the latest release from [Releases](https://github.com/syluse/SySubs/releases)
2. Extract the zip anywhere
3. Run `SySubs.exe`
4. Select a video or audio file, pick a model, click **Transcribe Now**

Models download automatically on first use.

## About the AI

SySubs uses **speech-to-text models** (OpenAI Whisper via faster-whisper), not generative AI. It does not create, rewrite, or generate new content, it only transcribes what was already spoken in your media files.

**No data is collected.** Everything runs locally on your machine. Your files, audio, and transcriptions never leave your computer. The only network requests made are for downloading models (which you explicitly choose to install).

Created by [Syluse](https://github.com/syluse) / [@Syluse_](https://x.com/Syluse_)

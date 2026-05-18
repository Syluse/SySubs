# SySubs TODO

## Customization & Text Formatting
- [x] **Text transform** — option to output all UPPERCASE or all lowercase
- [x] **Strip punctuation** — option to remove punctuation marks from subtitle text
- [x] **Combined** — allow both settings to apply together (e.g. uppercase + no punctuation)
- [x] **UI** — add text formatting controls to the settings panel or config section
- [x] **Persist** — save formatting preferences to config.json

## Repository & Distribution
- [x] **Initialize Git repo** — `git init`, create `.gitignore` (Python, Windows, PyInstaller)
- [x] **Create GitHub repository** — push code to GitHub
- [x] **PyInstaller spec** — create `.spec` file with icon, hidden imports, ffmpeg bundling
- [x] **Build script** — automate PyInstaller build + zip packaging (`scripts/build.ps1`)
- [x] **GitHub Releases** — set up release workflow for portable `.zip` distribution

## Future Features (v2+)
- [ ] Batch file processing — queue multiple files, shared or per-file settings
- [ ] SRT preview — review subtitles before export, with basic editing
- [ ] Auto-update mechanism — check GitHub Releases API on launch
- [ ] Speaker diarization — label who says what
- [ ] Translation mode — translate transcribed text to English
- [ ] Model caching — keep loaded model in memory across jobs

# YouTube Download Setup Guide

За да работи функцията за изтегляне на видеа от YouTube, трябва да инсталирате следните инструменти:

## 1. yt-dlp

### Windows:
```powershell
# С използване на pip (препоръчително)
pip install yt-dlp

# Или с използване на winget
winget install yt-dlp

# Или с използване на chocolatey
choco install yt-dlp
```

### Linux/Mac:
```bash
# С pip
pip install yt-dlp

# Или с пакетен мениджър
# Ubuntu/Debian:
sudo apt install yt-dlp

# macOS:
brew install yt-dlp
```

### Проверка:
```bash
yt-dlp --version
```

## 2. FFmpeg (за обработка на видеа и keyframes)

### Windows:
1. Изтеглете от: https://ffmpeg.org/download.html
2. Или с winget:
```powershell
winget install FFmpeg
```
3. Или с chocolatey:
```powershell
choco install ffmpeg
```

**Важно:** След инсталация, добавете FFmpeg към PATH:
- Отворете "Edit environment variables" в Windows
- Добавете `C:\ffmpeg\bin` (или където е инсталиран) към PATH
- Рестартирайте терминала/приложението

### Linux:
```bash
# Ubuntu/Debian:
sudo apt update
sudo apt install ffmpeg

# Fedora:
sudo dnf install ffmpeg

# Arch:
sudo pacman -S ffmpeg
```

### macOS:
```bash
brew install ffmpeg
```

### Проверка:
```bash
ffmpeg -version
ffprobe -version
```

## 3. Проверка на инсталацията

След инсталация, рестартирайте приложението и опитайте да изтеглите видео от YouTube.

## Как да използвате функцията:

1. Отворете приложението
2. Кликнете на "More" менюто в header-а
3. Изберете "YouTube Download"
4. Въведете пълен YouTube URL, например:
   - `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
   - `https://youtu.be/dQw4w9WgXcQ`
   - `https://www.youtube.com/shorts/VIDEO_ID`

5. Кликнете "Info" за да видите информация за видеото
6. Кликнете "Download" за да изтеглите

## Поддържани функции:

- ✅ Изтегляне на видеа до 1080p
- ✅ Автоматично извличане на субтитри (множество езици)
- ✅ Извличане на keyframes (рамки на всеки 30 секунди)
- ✅ Автоматично добавяне в галерията
- ✅ Търсене по субтитри

## Решаване на проблеми:

### Грешка: "Invalid YouTube URL"
- Уверете се, че въвеждате пълен URL, не само "youtube"
- Примери за валидни URL-и:
  - `https://www.youtube.com/watch?v=VIDEO_ID`
  - `https://youtu.be/VIDEO_ID`

### Грешка: "yt-dlp not found"
- Уверете се, че yt-dlp е инсталиран: `yt-dlp --version`
- Проверете дали е в PATH

### Грешка: "ffmpeg not found"
- Уверете се, че FFmpeg е инсталиран: `ffmpeg -version`
- Проверете дали е в PATH
- Рестартирайте приложението след добавяне към PATH

### Видеото не се изтегля:
- Проверете интернет връзката
- Някои видеа може да са защитени от изтегляне
- Опитайте друг формат или качество


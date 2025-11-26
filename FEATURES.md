# AI Gallery - Features Documentation

## Overview
AI Gallery is a comprehensive media management application with AI-powered analysis, video processing, and Telegram integration.

---

## Core Features

### 1. Image Management
- **Gallery View** - Grid layout with thumbnails, lazy loading
- **Image Detail Modal** - Full-size preview with metadata
- **Favorites** - Mark images as favorites
- **Tags** - AI-generated and manual tagging
- **Search** - Full-text search across descriptions and tags
- **Boards** - Organize images into hierarchical collections
- **Duplicate Detection** - Perceptual hash-based duplicate finding

### 2. AI Analysis
- **Multiple Styles**:
  - Classic - Detailed descriptions (2-4 sentences)
  - Artistic - Poetic, creative descriptions
  - Spicy - Bold, attention-grabbing style
  - Social Media - Optimized for Instagram/Facebook
  - Tags Only - Just keywords, no description
  - Custom - User-defined prompts
- **Auto-tagging** - Automatic tag generation
- **Filename Suggestions** - AI-suggested descriptive filenames
- **Batch Processing** - Analyze multiple images in parallel

### 3. Board System
- **Hierarchical Boards** - Parent/child board structure
- **AI Board Suggestions** - Auto-categorization recommendations
- **Drag & Drop** - Easy image organization
- **Board Covers** - Custom cover images

---

## Video Features

### 4. Video Download
**Supported Platforms:**
- YouTube (with quality selection: 360p-4K)
- TikTok
- Facebook
- Instagram Reels
- Twitter/X

**Options:**
- Quality selection (360p, 480p, 720p, 1080p, 1440p, 4K)
- Subtitle download (auto-generated or original)
- Keyframe extraction

### 5. Subtitle/Teleprompter Panel
- **Karaoke Mode** - Synchronized highlighting with video
- **Teleprompter Mode** - Large text, auto-scroll
- **Language Selection** - Switch between available languages
- **Resizable Panel** - Drag to resize
- **Click to Seek** - Click subtitle to jump to that moment

### 6. Video Bookmarks
- **Add Bookmarks** - Mark important moments
- **Visual Markers** - Colored markers on video timeline
- **Click to Jump** - Navigate to bookmarked time
- **Custom Colors** - Color-code your bookmarks

### 7. Video Notes (Timestamped)
- **Add Notes** - Write notes at specific timestamps
- **Auto-timestamp** - Notes linked to current time
- **View All Notes** - List view with timestamps
- **Export to Markdown** - Download notes as .md file
- **Click to Jump** - Navigate to note timestamp

### 8. Frame Capture (Screenshot)
- **Capture Current Frame** - Save frame as image
- **Auto-naming** - Includes timestamp in filename
- **Add to Gallery** - Automatically added with video's tags
- **High Quality** - JPEG with quality setting

### 9. A-B Loop
- **Set Point A** - Mark loop start
- **Set Point B** - Mark loop end
- **Continuous Loop** - Video repeats between A and B
- **Perfect for**: Learning dances, transcription, analysis

### 10. Video Clips Export
- **Select Time Range** - Start and end timestamps
- **Export as MP4** - Download clip file
- **Preserve Quality** - Re-encoded with libx264

### 11. Transcript Export
**Formats:**
- TXT (plain text)
- TXT with timestamps
- SRT (SubRip)
- VTT (WebVTT)
- JSON

### 12. AI Video Summary
- **Transcript Analysis** - AI reads subtitles
- **Key Topics** - Bullet points of main themes
- **Notable Moments** - Important timestamps
- **Copy to Clipboard** - Easy sharing

### 13. Transcript Search
- **Search Within Video** - Find specific words/phrases
- **Jump to Results** - Click to navigate
- **Highlight Matches** - Visual indication

---

## Telegram Integration

### 14. Telegram Bot
- **Auto-save Photos** - Photos sent to bot are saved to gallery
- **Auto-analyze** - AI analysis on upload
- **Video Download** - Send link, bot downloads video
- **Board Selection** - Choose board via inline buttons
- **Status Command** - Check gallery statistics

**Supported Video Links:**
- YouTube, TikTok, Facebook, Instagram, Twitter/X

---

## User Interface

### 15. UI Features
- **Dark Theme** - Modern dark color scheme
- **Responsive Design** - Works on desktop and mobile
- **Keyboard Shortcuts** - Navigation with arrow keys
- **Toast Notifications** - Feedback messages
- **Modal System** - Detail views, dialogs
- **Infinite Scroll** - Load more on scroll

### 16. Image Actions
- **Open in External App** - Configure preferred apps
- **Copy to Clipboard** - Copy image
- **Download** - Save to device
- **Delete** - Remove from gallery
- **Edit Tags** - Modify tags manually
- **Rename** - Change filename

---

## Technical Details

### API Endpoints

#### Images
```
GET  /api/images              - List images
GET  /api/images/:id          - Get image details
POST /api/images/:id/analyze  - AI analysis
DELETE /api/images/:id        - Delete image
```

#### Videos
```
POST /api/videos/download     - Download video
GET  /api/images/:id/subtitles - Get subtitles
POST /api/images/:id/clip     - Create video clip
POST /api/images/:id/capture-frame - Screenshot
POST /api/images/:id/summary  - AI summary
```

#### Bookmarks & Notes
```
GET/POST /api/images/:id/bookmarks - Manage bookmarks
GET/POST /api/images/:id/notes     - Manage notes
GET /api/images/:id/notes/export   - Export as markdown
```

#### Boards
```
GET  /api/boards              - List boards
POST /api/boards              - Create board
POST /api/images/:id/boards   - Add to board
```

### Database Schema
- `images` - Main media table
- `boards` - Board hierarchy
- `image_boards` - Many-to-many relation
- `youtube_videos` - Video metadata
- `video_subtitles` - Subtitle entries
- `video_keyframes` - Extracted frames
- `video_bookmarks` - Timestamp bookmarks
- `video_notes` - Timestamped notes

### Technologies
- **Backend**: Flask (Python)
- **Database**: SQLite
- **AI**: LM Studio (local LLM)
- **Video**: yt-dlp, FFmpeg
- **Frontend**: Vanilla JS, CSS
- **Bot**: python-telegram-bot

---

## Planned Features
- [ ] Language Reactor-style word lookup in subtitles
- [ ] Vocabulary saving and learning
- [ ] Translation integration
- [ ] Video chapters auto-detection
- [ ] Collaborative boards
- [ ] Cloud sync

---

*Last updated: November 2025*

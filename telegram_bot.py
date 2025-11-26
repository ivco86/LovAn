#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot for AI Gallery
Automatically saves photos from Telegram groups to the gallery and analyzes them with AI
"""

import os
import sys
import asyncio
import logging
import mimetypes
from pathlib import Path
from datetime import datetime
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import requests
from database import Database
from youtube_service import YouTubeService

# Thread pool for running blocking operations
_executor = ThreadPoolExecutor(max_workers=4)

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
GALLERY_API_URL = os.getenv('GALLERY_API_URL', 'http://localhost:5000')
PHOTOS_DIR = os.getenv('PHOTOS_DIR', 'photos')
AUTO_ANALYZE = os.getenv('AUTO_ANALYZE', 'true').lower() == 'true'
AI_STYLE = os.getenv('AI_STYLE', 'classic')  # classic, detailed, tags, custom

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v'}

# Allowed group/user IDs (empty = allow all)
ALLOWED_CHATS = os.getenv('ALLOWED_CHATS', '').split(',') if os.getenv('ALLOWED_CHATS') else []

# Ensure photos directory exists
os.makedirs(PHOTOS_DIR, exist_ok=True)

# Database instance
db = Database()

# YouTube service
youtube_service = YouTubeService(db)


class TelegramGalleryBot:
    """Telegram bot for saving photos to AI Gallery"""

    def __init__(self, token: str):
        self.token = token
        self.app = None

    async def _run_blocking(self, func, *args, **kwargs):
        """Run a blocking function in a thread executor to avoid blocking the event loop"""
        loop = asyncio.get_event_loop()
        if kwargs:
            func_with_kwargs = partial(func, *args, **kwargs)
            return await loop.run_in_executor(_executor, func_with_kwargs)
        return await loop.run_in_executor(_executor, func, *args)

    def _sanitize_token(self, value: str) -> str:
        return ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in value)
    
    def _build_filename(self, update: Update, original_name: str, default_ext: str,
                        allowed_exts=None) -> str:
        """
        Build a safe filename using the original name when available.
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        user = update.effective_user
        username = (user.username or user.first_name or "user") if user else "user"
        safe_username = self._sanitize_token(username) or "user"
        
        base_name = Path(original_name).name if original_name else ""
        stem = Path(base_name).stem if base_name else ""
        ext = Path(base_name).suffix.lower() if base_name else ""
        
        if not stem:
            stem = f"telegram_{safe_username}_{timestamp}"
        
        if not ext:
            ext = default_ext
        elif allowed_exts and ext not in allowed_exts:
            ext = default_ext
        
        safe_stem = self._sanitize_token(stem)
        return f"{safe_stem}{ext}"
    
    def _guess_extension(self, mime_type: str, fallback: str) -> str:
        if mime_type:
            guessed = mimetypes.guess_extension(mime_type)
            if guessed:
                return guessed
        return fallback
    
    async def _run_analysis(self, update: Update, image_id: int):
        await update.message.reply_text("🤖 Analyzing with AI...")
        try:
            # Run blocking request in thread pool
            response = await self._run_blocking(
                requests.post,
                f"{GALLERY_API_URL}/api/images/{image_id}/analyze",
                json={'style': AI_STYLE},
                timeout=120
            )

            if response.ok:
                data = response.json()
                description = data.get('description', 'No description')
                tags = data.get('tags', [])
                tags_text = ', '.join(tags[:5]) if tags else 'No tags'

                await update.message.reply_text(
                    f"✨ *Analysis Complete!*\n\n"
                    f"📝 {description}\n\n"
                    f"🏷️ Tags: {tags_text}",
                    parse_mode='Markdown'
                )
            else:
                logger.error(f"Analysis API error: {response.status_code}")
                await update.message.reply_text("⚠️ AI analysis failed (API error)")
        except requests.Timeout:
            logger.error("Analysis timeout")
            await update.message.reply_text("⚠️ AI analysis timeout (will retry later)")
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            await update.message.reply_text(f"⚠️ AI analysis error: {str(e)}")
    
    async def _process_media(self, update: Update, telegram_file, filename: str,
                             media_type: str, width=None, height=None, file_size=None):
        filepath = os.path.join(PHOTOS_DIR, filename)
        await telegram_file.download_to_drive(filepath)
        
        chat = update.effective_chat
        chat_name = chat.title or chat.username or chat.id
        media_label = "Video" if media_type == 'video' else "Image"
        logger.info(f"Downloaded {media_label.lower()} from {chat_name}: {filename}")
        
        image_id = db.add_image(
            filepath,
            filename=filename,
            width=width,
            height=height,
            file_size=file_size,
            media_type=media_type
        )
        
        if image_id:
            await update.message.reply_text(
                f"✅ {media_label} saved to gallery!\n"
                f"📝 File: `{filename}`\n"
                f"🆔 Image ID: {image_id}",
                parse_mode='Markdown'
            )
            
            if AUTO_ANALYZE:
                await self._run_analysis(update, image_id)
        else:
            await update.message.reply_text(f"❌ Failed to add {media_label.lower()} to gallery")
        
        return image_id

    async def send_photo_to_chat(self, chat_id: int, filepath: str, caption: str = None):
        """
        Send a photo from the gallery to a Telegram chat

        Args:
            chat_id: Telegram chat ID (group or user)
            filepath: Path to the photo file
            caption: Optional caption for the photo

        Returns:
            dict: Result with success status and message
        """
        try:
            if not os.path.exists(filepath):
                return {'success': False, 'error': 'File not found'}

            # Check if file is an image
            ext = Path(filepath).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                return {'success': False, 'error': 'Not a valid image file'}

            # Send photo using the application's bot
            with open(filepath, 'rb') as photo_file:
                message = await self.app.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=caption,
                    parse_mode='Markdown' if caption else None
                )

            logger.info(f"Photo sent to chat {chat_id}: {filepath}")
            return {
                'success': True,
                'message_id': message.message_id,
                'chat_id': chat_id
            }

        except Exception as e:
            logger.error(f"Error sending photo to chat {chat_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type

        welcome_msg = (
            "🖼️ *AI Gallery Bot*\n\n"
            "I automatically save photos to your AI Gallery and analyze them with AI!\n\n"
            "*How to use:*\n"
            "• Send me a photo or add me to a group\n"
            "• I'll automatically save and analyze all photos\n"
            "• Use /status to check my status\n\n"
            f"*Current chat:*\n"
            f"• ID: `{chat_id}`\n"
            f"• Type: {chat_type}\n\n"
            f"*Settings:*\n"
            f"• Auto-analyze: {'✅' if AUTO_ANALYZE else '❌'}\n"
            f"• AI Style: {AI_STYLE}\n"
        )

        await update.message.reply_text(welcome_msg, parse_mode='Markdown')

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            # Get gallery stats - run blocking request in thread pool
            response = await self._run_blocking(
                requests.get,
                f"{GALLERY_API_URL}/api/health",
                timeout=5
            )
            if response.ok:
                data = response.json()
                stats = data.get('stats', {})

                status_msg = (
                    "📊 *Gallery Status*\n\n"
                    f"• Total Images: {stats.get('total_images', 0)}\n"
                    f"• Analyzed: {stats.get('analyzed_images', 0)}\n"
                    f"• Unanalyzed: {stats.get('unanalyzed_images', 0)}\n"
                    f"• Favorites: {stats.get('favorite_images', 0)}\n"
                    f"• Boards: {stats.get('total_boards', 0)}\n\n"
                    f"• AI Status: {'🟢 Connected' if data.get('ai_connected') else '🔴 Offline'}\n"
                    f"• Bot Status: 🟢 Active\n"
                )
            else:
                status_msg = "⚠️ Cannot connect to gallery API"

        except Exception as e:
            logger.error(f"Error getting status: {e}")
            status_msg = f"❌ Error: {str(e)}"

        await update.message.reply_text(status_msg, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_msg = (
            "🤖 *Bot Commands*\n\n"
            "/start - Show welcome message\n"
            "/status - Check gallery statistics\n"
            "/download <url> - Download video manually\n"
            "/help - Show this help message\n\n"
            "*Auto Video Download:*\n"
            "Just paste a video link and I'll download it automatically!\n\n"
            "*Supported platforms:*\n"
            "🎬 YouTube (720p + auto subtitles)\n"
            "🎵 TikTok\n"
            "📘 Facebook\n"
            "📷 Instagram Reels\n"
            "🐦 Twitter/X\n\n"
            "*Features:*\n"
            "• Automatic photo saving\n"
            "• AI analysis with descriptions and tags\n"
            "• Video downloading with subtitles\n"
            "• Works in groups and private chats\n"
        )

        await update.message.reply_text(help_msg, parse_mode='Markdown')

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /download command for YouTube videos"""
        chat_id = update.effective_chat.id

        # Check if chat is allowed
        if not self.is_chat_allowed(chat_id):
            logger.warning(f"Ignoring download from unauthorized chat: {chat_id}")
            return

        # Get URL from command arguments
        if not context.args:
            await update.message.reply_text(
                "📥 *YouTube Download*\n\n"
                "Usage: `/download <youtube_url>`\n\n"
                "Example:\n"
                "`/download https://youtube.com/watch?v=dQw4w9WgXcQ`",
                parse_mode='Markdown'
            )
            return

        url = context.args[0]

        # Validate URL
        youtube_id = youtube_service.extract_youtube_id(url)
        if not youtube_id:
            await update.message.reply_text(
                "❌ Invalid YouTube URL\n\n"
                "Please provide a valid YouTube link."
            )
            return

        # Check if video already exists
        existing = db.get_youtube_video_by_youtube_id(youtube_id)
        if existing:
            await update.message.reply_text(
                f"ℹ️ *Video already in gallery*\n\n"
                f"📺 {existing.get('title', 'Unknown')}\n"
                f"🎬 Channel: {existing.get('channel_name', 'Unknown')}\n"
                f"⏱️ Duration: {youtube_service.format_duration(existing.get('duration', 0))}\n"
                f"🆔 ID: {existing.get('id')}",
                parse_mode='Markdown'
            )
            return

        # Send initial status message
        status_msg = await update.message.reply_text(
            "🔍 Getting video information...",
            parse_mode='Markdown'
        )

        try:
            # Get video info first - run in thread pool
            info = await self._run_blocking(youtube_service.get_video_info, url)
            if not info:
                await status_msg.edit_text("❌ Failed to get video information")
                return

            # Show video info and start download
            await status_msg.edit_text(
                f"📥 *Downloading...*\n\n"
                f"📺 {info.get('title', 'Unknown')}\n"
                f"🎬 {info.get('channel_name', 'Unknown')}\n"
                f"⏱️ {youtube_service.format_duration(info.get('duration', 0))}\n"
                f"👁️ {youtube_service.format_views(info.get('view_count', 0))} views\n\n"
                f"⏳ This may take a few minutes...",
                parse_mode='Markdown'
            )

            # Download video - run in thread pool
            result = await self._run_blocking(youtube_service.download_video, url)

            if not result:
                await status_msg.edit_text("❌ Download failed. Please try again.")
                return

            if result.get('status') == 'exists':
                video = result.get('video', {})
                await status_msg.edit_text(
                    f"ℹ️ *Video already exists*\n\n"
                    f"📺 {video.get('title', 'Unknown')}\n"
                    f"🆔 ID: {video.get('id')}",
                    parse_mode='Markdown'
                )
                return

            # Success message
            keyframe_count = len(result.get('keyframes', []))
            subtitle_langs = list(result.get('parsed_subtitles', {}).keys())

            success_msg = (
                f"✅ *Download Complete!*\n\n"
                f"📺 {result.get('title', 'Unknown')}\n"
                f"⏱️ Duration: {youtube_service.format_duration(result.get('duration', 0))}\n"
                f"📐 Resolution: {result.get('width', 0)}x{result.get('height', 0)}\n"
            )

            if keyframe_count > 0:
                success_msg += f"🖼️ Keyframes: {keyframe_count}\n"

            if subtitle_langs:
                success_msg += f"💬 Subtitles: {', '.join(subtitle_langs)}\n"

            success_msg += f"\n🆔 Gallery ID: {result.get('image_id', 'N/A')}"

            await status_msg.edit_text(success_msg, parse_mode='Markdown')

            # Send thumbnail if available
            thumbnail_url = info.get('thumbnail_url')
            if thumbnail_url:
                try:
                    await update.message.reply_photo(
                        photo=thumbnail_url,
                        caption=f"🎬 {info.get('title', '')}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send thumbnail: {e}")

        except Exception as e:
            logger.error(f"Error in download command: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Error: {str(e)}")

    def is_chat_allowed(self, chat_id: int) -> bool:
        """Check if chat is allowed to use the bot"""
        if not ALLOWED_CHATS:
            return True  # Allow all if no restrictions
        return str(chat_id) in ALLOWED_CHATS

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming photos"""
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or update.effective_chat.username or "Unknown"

        # Check if chat is allowed
        if not self.is_chat_allowed(chat_id):
            logger.warning(f"Ignoring photo from unauthorized chat: {chat_id}")
            return

        try:
            # Get the largest photo
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            filename = self._build_filename(update, None, '.jpg', IMAGE_EXTENSIONS)

            await self._process_media(
                update,
                file,
                filename,
                media_type='image',
                width=getattr(photo, 'width', None),
                height=getattr(photo, 'height', None),
                file_size=getattr(photo, 'file_size', None)
            )

        except Exception as e:
            logger.error(f"Error handling photo: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming videos"""
        chat_id = update.effective_chat.id

        if not self.is_chat_allowed(chat_id):
            logger.warning(f"Ignoring video from unauthorized chat: {chat_id}")
            return

        try:
            video = update.message.video
            if not video:
                return

            file = await context.bot.get_file(video.file_id)
            default_ext = self._guess_extension(video.mime_type, '.mp4')
            filename = self._build_filename(update, video.file_name, default_ext, VIDEO_EXTENSIONS)

            await self._process_media(
                update,
                file,
                filename,
                media_type='video',
                width=getattr(video, 'width', None),
                height=getattr(video, 'height', None),
                file_size=getattr(video, 'file_size', None)
            )
        except Exception as e:
            logger.error(f"Error handling video: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming documents (uncompressed photos or videos)"""
        chat_id = update.effective_chat.id

        # Check if chat is allowed
        if not self.is_chat_allowed(chat_id):
            return

        document = update.message.document

        mime_type = document.mime_type or ''
        media_type = None
        allowed_exts = None
        default_ext = '.jpg'

        if mime_type.startswith('image/'):
            media_type = 'image'
            allowed_exts = IMAGE_EXTENSIONS
            default_ext = self._guess_extension(mime_type, '.jpg')
        elif mime_type.startswith('video/'):
            media_type = 'video'
            allowed_exts = VIDEO_EXTENSIONS
            default_ext = self._guess_extension(mime_type, '.mp4')

        if not media_type:
            logger.info(f"Ignoring unsupported document type: {mime_type}")
            return

        try:
            file = await context.bot.get_file(document.file_id)
            filename = self._build_filename(update, document.file_name, default_ext, allowed_exts)

            await self._process_media(
                update,
                file,
                filename,
                media_type=media_type,
                file_size=getattr(document, 'file_size', None)
            )
        except Exception as e:
            logger.error(f"Error handling document: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    def _get_boards_keyboard(self, video_url: str, include_none: bool = True) -> InlineKeyboardMarkup:
        """Create inline keyboard with available boards"""
        boards = db.get_all_boards()
        keyboard = []

        # Add "No Board" option first
        if include_none:
            keyboard.append([InlineKeyboardButton("📂 No Board (just gallery)", callback_data=f"board:0:{video_url[:60]}")])

        # Group boards by parent (show hierarchy)
        root_boards = [b for b in boards if not b.get('parent_id')]
        for board in root_boards[:8]:  # Limit to 8 root boards
            btn_text = f"📁 {board['name']}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"board:{board['id']}:{video_url[:60]}")])

            # Add sub-boards indented
            sub_boards = [b for b in boards if b.get('parent_id') == board['id']]
            for sub in sub_boards[:3]:  # Limit sub-boards
                btn_text = f"  └ {sub['name']}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"board:{sub['id']}:{video_url[:60]}")])

        # Add cancel button
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="board:cancel:")])

        return InlineKeyboardMarkup(keyboard)

    async def handle_board_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle board selection callback from inline keyboard"""
        query = update.callback_query
        await query.answer()

        data = query.data
        if not data.startswith("board:"):
            return

        parts = data.split(":", 2)
        if len(parts) < 2:
            return

        board_selection = parts[1]

        # Handle cancel
        if board_selection == "cancel":
            await query.edit_message_text("❌ Download cancelled")
            if 'pending_video' in context.user_data:
                del context.user_data['pending_video']
            return

        # Get pending video info
        pending = context.user_data.get('pending_video')
        if not pending:
            await query.edit_message_text("⚠️ Session expired. Please send the link again.")
            return

        board_id = int(board_selection) if board_selection != "0" else None
        url = pending['url']
        platform = pending['platform']
        info = pending['info']
        quality = pending['quality']
        download_subtitles = pending['download_subtitles']
        original_subtitles = pending['original_subtitles']
        platform_emoji = pending['platform_emoji']

        # Get board name for message
        board_name = "No Board"
        if board_id:
            board = db.get_board(board_id)
            if board:
                board_name = board['name']

        # Update message to show downloading
        quality_text = '720p' if quality == '720' else 'Best'
        await query.edit_message_text(
            f"📥 *Downloading from {platform.title()}...*\n\n"
            f"📺 {info.get('title', 'Unknown')[:50]}...\n"
            f"🎬 {info.get('channel_name', 'Unknown')}\n"
            f"⏱️ {youtube_service.format_duration(info.get('duration', 0))}\n"
            f"📐 Quality: {quality_text}\n"
            f"💬 Subtitles: {'Auto-generated' if download_subtitles else 'None'}\n"
            f"📁 Board: {board_name}\n\n"
            f"⏳ Please wait...",
            parse_mode='Markdown'
        )

        try:
            # Download video with appropriate settings - run in thread pool
            result = await self._run_blocking(
                youtube_service.download_video,
                url,
                download_subtitles=download_subtitles,
                original_subtitles=original_subtitles,
                quality=quality
            )

            if not result:
                await query.edit_message_text(f"❌ Download failed from {platform}")
                return

            if result.get('status') == 'exists':
                video = result.get('video', {})
                await query.edit_message_text(
                    f"ℹ️ *Video already exists*\n\n"
                    f"📺 {video.get('title', 'Unknown')}\n"
                    f"🆔 ID: {video.get('id')}",
                    parse_mode='Markdown'
                )
                return

            # Add to board if selected
            image_id = result.get('image_id')
            if board_id and image_id:
                db.add_image_to_board(image_id, board_id)

            # Success message
            keyframe_count = len(result.get('keyframes', []))
            subtitle_langs = list(result.get('parsed_subtitles', {}).keys())

            success_msg = (
                f"✅ *Download Complete!*\n\n"
                f"{platform_emoji} Platform: {platform.title()}\n"
                f"📺 {result.get('title', 'Unknown')[:50]}\n"
                f"⏱️ Duration: {youtube_service.format_duration(result.get('duration', 0))}\n"
                f"📐 {result.get('width', 0)}x{result.get('height', 0)}\n"
            )

            if keyframe_count > 0:
                success_msg += f"🖼️ Keyframes: {keyframe_count}\n"

            if subtitle_langs:
                success_msg += f"💬 Subtitles: {', '.join(subtitle_langs)}\n"

            if board_id:
                success_msg += f"📁 Board: {board_name}\n"

            success_msg += f"\n🆔 Gallery ID: {image_id or 'N/A'}"

            await query.edit_message_text(success_msg, parse_mode='Markdown')

            # Clean up pending data
            del context.user_data['pending_video']

            # Send thumbnail if available
            thumbnail_url = info.get('thumbnail_url')
            if thumbnail_url:
                try:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=thumbnail_url,
                        caption=f"🎬 {info.get('title', '')[:100]}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send thumbnail: {e}")

        except Exception as e:
            logger.error(f"Error downloading from link: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error: {str(e)}")

    async def handle_text_with_links(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages that may contain video URLs"""
        chat_id = update.effective_chat.id

        if not self.is_chat_allowed(chat_id):
            return

        text = update.message.text or update.message.caption or ""
        if not text:
            return

        # Detect video URLs
        import re
        video_url_patterns = [
            # YouTube
            r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+)',
            r'(https?://youtu\.be/[\w-]+)',
            r'(https?://(?:www\.)?youtube\.com/shorts/[\w-]+)',
            # TikTok
            r'(https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+)',
            r'(https?://(?:vm\.)?tiktok\.com/[\w]+)',
            # Facebook
            r'(https?://(?:www\.)?facebook\.com/.+/videos/\d+)',
            r'(https?://fb\.watch/[\w]+)',
            # Instagram
            r'(https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w-]+)',
            # Twitter/X
            r'(https?://(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+)',
        ]

        urls_found = []
        for pattern in video_url_patterns:
            matches = re.findall(pattern, text)
            urls_found.extend(matches)

        if not urls_found:
            return

        # Process first URL found
        url = urls_found[0]
        platform = youtube_service.detect_platform(url)

        # Determine settings based on platform
        if platform == 'youtube':
            # YouTube: 720p, auto subtitles
            quality = '720'
            download_subtitles = True
            original_subtitles = False  # Auto-generated only
        else:
            # Other platforms: best quality, no subtitles
            quality = 'best'
            download_subtitles = False
            original_subtitles = False

        # Send initial status message
        platform_emoji = {
            'youtube': '🎬',
            'tiktok': '🎵',
            'facebook': '📘',
            'instagram': '📷',
            'twitter': '🐦',
        }.get(platform, '📺')

        status_msg = await update.message.reply_text(
            f"{platform_emoji} Detected {platform.title()} video link...\n"
            f"🔍 Getting video information...",
            parse_mode='Markdown'
        )

        try:
            # Get video info first - run in thread pool
            info = await self._run_blocking(youtube_service.get_video_info, url)
            if not info:
                await status_msg.edit_text(f"❌ Failed to get video information from {platform}")
                return

            # Check if already exists
            video_id = youtube_service.extract_video_id(url)
            existing = db.get_youtube_video_by_youtube_id(video_id)
            if existing:
                await status_msg.edit_text(
                    f"ℹ️ *Video already in gallery*\n\n"
                    f"📺 {existing.get('title', 'Unknown')}\n"
                    f"🆔 ID: {existing.get('id')}",
                    parse_mode='Markdown'
                )
                return

            # Store pending video info for callback
            context.user_data['pending_video'] = {
                'url': url,
                'platform': platform,
                'info': info,
                'quality': quality,
                'download_subtitles': download_subtitles,
                'original_subtitles': original_subtitles,
                'platform_emoji': platform_emoji
            }

            # Show video info and board selection
            quality_text = '720p' if quality == '720' else 'Best'
            keyboard = self._get_boards_keyboard(url)

            await status_msg.edit_text(
                f"{platform_emoji} *{platform.title()} Video Found*\n\n"
                f"📺 {info.get('title', 'Unknown')[:60]}...\n"
                f"🎬 {info.get('channel_name', 'Unknown')}\n"
                f"⏱️ {youtube_service.format_duration(info.get('duration', 0))}\n"
                f"📐 Quality: {quality_text}\n"
                f"💬 Subtitles: {'Auto-generated' if download_subtitles else 'None'}\n\n"
                f"📁 *Select a board:*",
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Error processing video link: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Error: {str(e)}")

    def run(self):
        """Start the bot"""
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set!")
            print("❌ Error: TELEGRAM_BOT_TOKEN environment variable is not set")
            print("\nHow to set it:")
            print("  export TELEGRAM_BOT_TOKEN='your_token_here'")
            print("\nOr create a .env file with:")
            print("  TELEGRAM_BOT_TOKEN=your_token_here")
            return

        logger.info("Starting Telegram Gallery Bot...")

        # Create application
        self.app = Application.builder().token(self.token).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("download", self.download_command))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VIDEO, self.handle_video))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        # Auto-detect video links in text messages
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text_with_links
        ))
        # Handle board selection callbacks
        self.app.add_handler(CallbackQueryHandler(self.handle_board_selection, pattern=r'^board:'))

        # Start bot
        print("🤖 Telegram Gallery Bot is running...")
        print(f"📁 Photos directory: {PHOTOS_DIR}")
        print(f"🌐 Gallery API: {GALLERY_API_URL}")
        print(f"🤖 Auto-analyze: {AUTO_ANALYZE}")
        print(f"🎨 AI Style: {AI_STYLE}")
        if ALLOWED_CHATS:
            print(f"🔒 Allowed chats: {', '.join(ALLOWED_CHATS)}")
        else:
            print("🌍 Accepting photos from all chats")
        print("\nPress Ctrl+C to stop")

        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Main entry point"""
    bot = TelegramGalleryBot(TELEGRAM_BOT_TOKEN)
    bot.run()


if __name__ == '__main__':
    main()

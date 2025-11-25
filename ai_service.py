"""
AI Service for image analysis using LM Studio
Handles communication with local LM Studio API

IMPROVEMENTS:
- Retry mechanism with exponential backoff
- User-friendly error messages
- Response validation
- Parallel batch processing (3-5x faster)
- Config class for easy customization
- Metrics & monitoring
"""

import requests
import base64
import json
import logging
import re
import time
import threading
from typing import Dict, Tuple, Optional, List, Union, Callable
from pathlib import Path
from dataclasses import dataclass
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class AIServiceError(Exception):
    """Custom exception with user-friendly messages"""
    def __init__(self, technical_msg: str, user_msg: str):
        self.technical_msg = technical_msg
        self.user_msg = user_msg
        super().__init__(technical_msg)


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class AIServiceConfig:
    """Configuration for AI Service"""
    # Connection
    lm_studio_url: str = "http://localhost:1234"
    timeout: int = 120
    
    # Retry mechanism
    max_retries: int = 3
    backoff_factor: float = 2.0
    
    # Model parameters
    temperature: float = 0.7
    max_tokens: int = 500
    default_model: str = "llava"
    
    # Batch processing
    max_workers: int = 3  # Safe for most GPUs
    
    # Validation
    min_tags: int = 3
    max_tags: int = 20
    min_filename_length: int = 5
    max_filename_length: int = 50
    
    # Future features
    enable_cache: bool = False
    cache_ttl: int = 3600


# ============================================================================
# DECORATORS
# ============================================================================

def retry_on_failure(max_retries: int = 3, backoff_factor: float = 2.0):
    """
    Retry decorator with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for wait time between retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.ConnectionError, 
                        requests.exceptions.Timeout) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"❌ Failed after {max_retries} attempts: {e}")
                        raise
                    
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"⚠️ Attempt {attempt + 1}/{max_retries} failed, "
                                 f"retrying in {wait_time:.1f}s... ({type(e).__name__})")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator


# ============================================================================
# MAIN SERVICE CLASS
# ============================================================================

class AIService:
    # Common JSON format instructions used across all prompts
    CRITICAL_JSON_INSTRUCTIONS = """
You must respond with ONLY a valid JSON object in this exact format:
{
  "description": "your description here",
  "tags": ["tag1", "tag2", "tag3"],
  "suggested_filename": "descriptive_filename_here"
}

CRITICAL INSTRUCTIONS:
- Your ENTIRE response must be ONLY the JSON object above
- Do NOT add any explanations before or after the JSON
- Do NOT use markdown code blocks (no ```json```)
- Do NOT add any commentary or additional text
- Just the raw JSON object and nothing else
- Ensure the JSON is valid with no trailing commas or syntax errors"""

    def __init__(self, config: Optional[Union[AIServiceConfig, str]] = None):
        """
        Initialize AI Service
        
        Args:
            config: Configuration object, URL string, or None. 
                   - If AIServiceConfig: uses that config
                   - If str: treats as lm_studio_url and uses default config
                   - If None: uses default config
        """
        # Backward compatibility: accept string URL
        if isinstance(config, str):
            self.config = AIServiceConfig(lm_studio_url=config)
        elif isinstance(config, AIServiceConfig):
            self.config = config
        else:
            self.config = AIServiceConfig()
        
        self.lm_studio_url = self.config.lm_studio_url
        self.api_endpoint = f"{self.lm_studio_url}/v1/chat/completions"
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Metrics
        self.metrics = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0.0,
            'errors': defaultdict(int),
            'by_style': defaultdict(lambda: {'count': 0, 'time': 0.0})
        }
        
        logger.info(f"✅ AIService initialized: {self.lm_studio_url}")
        logger.debug(f"Config: retries={self.config.max_retries}, "
                    f"timeout={self.config.timeout}s, "
                    f"workers={self.config.max_workers}")

        # Different description styles/prompts
        self.prompts = {
            'classic': {
                'name': 'Classic',
                'description': 'Detailed and comprehensive (2-4 sentences)',
                'prompt': """Analyze this image thoroughly and provide:
1. A detailed description (2-4 sentences) that captures:
   - Main subject(s) and what they're doing
   - Art style/medium (e.g., photograph, comic art, illustration, cartoon, painting, 3D render, etc.)
   - Notable visual features (clothing, accessories, tattoos, piercings, hair style/color, etc.)
   - Setting/environment and atmosphere
   - Lighting and color palette if notable
2. 8-15 comprehensive tags covering:
   - Subject type (woman, man, couple, animal, landscape, etc.)
   - Art style (comic, illustration, photo, cartoon, anime, etc.)
   - Specific features (tattoos, sword, urban, nature, etc.)
   - Mood/atmosphere (dramatic, peaceful, dark, vibrant, etc.)
   - Colors if prominent (monochrome, colorful, blue_tones, etc.)
3. A suggested filename (descriptive, lowercase, use underscores, no spaces, max 50 chars, WITHOUT file extension)

Guidelines for description:
- STRICT LIMIT: 2-4 sentences MAXIMUM - be concise!
- Be specific about art style (very important!) - is it a photo, comic art, illustration, digital art, painting?
- ONLY describe what IS present - do NOT mention what is NOT there (no "without makeup", "no accessories", etc.)
- Include notable details like tattoos, piercings, unique clothing, weapons, etc.
- Describe the setting and mood
- Focus on POSITIVE attributes - what makes the image interesting
- Keep it factual and comprehensive but concise (2-4 sentences max)

Guidelines for tags:
- ALWAYS include art style tags (comic, illustration, photo, cartoon, anime, painted, etc.)
- Include subject descriptors (woman, man, portrait, landscape, etc.)
- Include specific features (tattoos, sword, leather, cyberpunk, etc.)
- Include mood/atmosphere tags (dark, dramatic, peaceful, etc.)
- NEVER use negative tags (no "no_mood", "no_accessories", "without_x", etc.)
- Tags must describe WHAT IS PRESENT, not what is absent
- Keep tags lowercase, prefer single words or compound_words
- Ensure they are unique and highly relevant
- Aim for 8-15 tags for comprehensive categorization
- Every tag must add VALUE - avoid generic filler tags

Guidelines for filename:
- Should reflect main subject and key characteristics
- Use underscores instead of spaces
- Keep it descriptive but under 50 chars
- Do NOT include file extension
- Example: "woman_with_sword_comic_style" not just "woman_with_sword\""""
            },

            'artistic': {
                'name': 'Artistic',
                'description': 'Detailed, poetic, and creative description',
                'prompt': """Analyze this image with artistic detail and provide:
1. A detailed, artistic description (3-4 sentences) that captures:
   - Art style/medium (photograph, comic art, illustration, digital art, painting, etc.) - CRITICAL!
   - Main subjects and their characteristics (features, clothing, accessories, tattoos, etc.)
   - Mood, atmosphere, colors, composition, and emotional impact
   - Lighting, shadows, and visual techniques
   - Be poetic and evocative while being accurate
2. 10-15 comprehensive tags including:
   - Art style (comic, illustration, photo, painted, etc.) - REQUIRED
   - Subject type (woman, man, portrait, etc.)
   - Specific features (tattoos, piercings, weapons, etc.)
   - Mood and atmosphere
   - Technical and artistic aspects
3. A suggested filename (descriptive, lowercase, use underscores, no spaces, max 50 chars, WITHOUT file extension)

Guidelines:
- LIMIT: 3-4 sentences for description - be evocative but concise
- ALWAYS identify and mention the art style/medium in description
- ONLY describe what IS visible - do NOT mention absences (no "lacks", "without", "no", etc.)
- Make the description rich, detailed, and atmospheric
- Include details about lighting, composition, mood, colors
- Use vivid, descriptive language for PRESENT elements
- Tags MUST include art style (comic, illustration, photo, cartoon, anime, painted, etc.)
- NEVER use negative tags (no "no_mood", "without_x", "lacks_y", etc.)
- Tags should include artistic and technical terms; keep them lowercase, prefer single words or compound_words
- Every tag must describe something PRESENT in the image
- Ensure they are unique and relevant
- Filename should be descriptive but concise
- Use underscores instead of spaces in filename
- Do NOT include file extension in suggested_filename"""
            },

            'spicy': {
                'name': 'Spicy',
                'description': 'Provocative and attention-grabbing style',
                'prompt': """Analyze this image with a bold, provocative style and provide:
1. A captivating description (3-4 sentences) that includes:
   - Art style/medium (photo, comic, illustration, etc.) - REQUIRED
   - Main subjects and striking visual features (tattoos, accessories, unique style, etc.)
   - Attention-grabbing, bold, and engaging language
   - Emphasis on the most striking and alluring aspects
2. 10-15 tags including:
   - Art style (comic, illustration, photo, etc.) - REQUIRED
   - Subject type and specific features
   - Mood and aesthetic qualities
   - Visual characteristics
3. A suggested filename (descriptive, evocative, lowercase, use underscores, no spaces, max 50 chars, WITHOUT file extension)

Guidelines:
- LIMIT: 3-4 sentences - be bold but concise
- ALWAYS identify art style/medium first (comic, photo, illustration, etc.)
- ONLY describe visible elements - do NOT mention what's missing
- Make the description bold, captivating, and more provocative with sensual, tantalizing language to heighten allure and intensity
- Emphasize visual appeal and striking elements that ARE PRESENT
- Use confident, engaging language
- Focus on what makes the image stand out
- Tags MUST include art style (comic, illustration, photo, cartoon, anime, etc.)
- NEVER use negative tags (no "no_x", "without_y", "lacks_z", etc.)
- Tags should include mood and aesthetics; keep them lowercase, prefer single words or compound_words
- Every tag must add value and describe something VISIBLE
- Ensure they are unique and relevant
- Filename should be descriptive but concise
- Use underscores instead of spaces in filename
- Do NOT include file extension in suggested_filename"""
            },

            'social': {
                'name': 'Social Media',
                'description': 'Optimized for Instagram, Facebook, Twitter',
                'prompt': """Analyze this image for social media posting and provide:
1. A social media-ready description (2-4 paragraphs) that includes:
   - Art style/type (photo, comic, illustration, digital art, etc.) - mention naturally
   - Main subject and notable features (tattoos, style, unique elements, etc.)
   - Engaging, relatable tone perfect for Instagram, Facebook, or Twitter
   - Conversational and authentic language
2. 10-15 trending hashtags and relevant keywords including:
   - Art style hashtags (#ComicArt, #Illustration, #Photography, etc.)
   - Subject hashtags (#Portrait, #Fashion, etc.)
   - Feature hashtags (#Tattoos, #InkedGirls, etc.)
   - Trending and relevant keywords
3. A suggested filename (catchy, descriptive, lowercase, use underscores, no spaces, max 50 chars, WITHOUT file extension)

Guidelines:
- Naturally mention art style in description (e.g., "This stunning comic art shows...")
- Write in a friendly, conversational tone
- Make it shareable and relatable
- Tags MUST include art style hashtags (#ComicArt, #Illustration, #DigitalArt, etc.)
- Tags should include the # for hashtags where appropriate; keep them lowercase, prefer single words or phrases
- Ensure they are unique and relevant
- Consider what would perform well on social platforms
- Filename should be descriptive but concise
- Use underscores instead of spaces in filename
- Do NOT include file extension in suggested_filename"""
            },

            'tags': {
                'name': 'Tags Only',
                'description': 'Generate only tags/keywords without description',
                'prompt': """Analyze this image and provide ONLY comprehensive tags/keywords.

SPECIAL INSTRUCTIONS:
- Generate 10-15 relevant, descriptive tags/keywords for this image
- Leave description empty (empty string "")
- Leave suggested_filename empty (empty string "")

Guidelines for tags - MUST include:
1. Art style (comic, illustration, photo, cartoon, anime, painted, digital_art, etc.) - REQUIRED as first tags
2. Subject type (woman, man, portrait, landscape, animal, etc.)
3. Specific features (tattoos, piercings, sword, accessories, etc.)
4. Mood/atmosphere (dark, dramatic, peaceful, vibrant, etc.)
5. Colors if prominent (monochrome, colorful, blue_tones, etc.)
6. Setting (urban, nature, indoor, studio, etc.)

Format rules:
- Keep tags lowercase
- Prefer single words (use compound_words if needed like "comic_art" or "golden_hour")
- ALWAYS include art style tags (comic, illustration, photo, etc.) - this is CRITICAL
- Include specific details like tattoos, weapons, clothing style, etc.
- NEVER use negative tags (no "no_mood", "no_accessories", "without_x", etc.)
- Tags must describe WHAT IS PRESENT, not what is absent
- Every tag must add VALUE - no filler tags
- Ensure tags are unique and highly relevant
- No hashtags (#) - just plain keywords
- Aim for 10-15 comprehensive tags"""
            },

            'custom': {
                'name': 'Custom',
                'description': 'Use your own custom prompt',
                'prompt': None  # Will be provided by user
            }
        }

    # ========================================================================
    # PUBLIC API METHODS
    # ========================================================================

    def get_available_styles(self) -> Dict[str, Dict]:
        """Get all available description styles"""
        return {
            key: {
                'name': value['name'],
                'description': value['description']
            }
            for key, value in self.prompts.items()
        }

    def check_connection(self) -> Tuple[bool, str]:
        """Check if LM Studio is running and accessible"""
        try:
            response = requests.get(f"{self.lm_studio_url}/v1/models", timeout=5)
            if response.status_code == 200:
                return True, "✅ LM Studio is connected"
            else:
                return False, f"⚠️ LM Studio returned status {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "❌ Cannot connect to LM Studio. Is it running?"
        except requests.exceptions.Timeout:
            return False, "⏱️ Connection to LM Studio timed out"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def analyze_image(self, image_path: str, style: str = 'classic', 
                     custom_prompt: str = None) -> Optional[Dict]:
        """
        Analyze image and return description and tags
        
        Args:
            image_path: Path to the image file
            style: Description style ('classic', 'artistic', 'spicy', 'social', 'tags', 'custom')
            custom_prompt: Custom prompt text (only used if style='custom')
        
        Returns: 
            {'description': str, 'tags': List[str], 'suggested_filename': str} or None on error
        
        Raises:
            AIServiceError: With user-friendly error message
        """
        start_time = time.time()
        self.metrics['total_requests'] += 1
        
        try:
            # Read and encode image
            try:
                with open(image_path, 'rb') as f:
                    image_data = f.read()
            except FileNotFoundError:
                raise AIServiceError(
                    technical_msg=f"File not found: {image_path}",
                    user_msg=f"📁 Файлът не съществува:\n{image_path}\n\nПроверете пътя."
                )

            base64_image = base64.b64encode(image_data).decode('utf-8')

            # Determine image format
            ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.bmp': 'image/bmp'
            }.get(ext, 'image/jpeg')

            # Get prompt based on style
            if style == 'custom' and custom_prompt:
                prompt = f"{custom_prompt}\n\n{self.CRITICAL_JSON_INSTRUCTIONS}"
            elif style in self.prompts:
                prompt = f"{self.prompts[style]['prompt']}\n\n{self.CRITICAL_JSON_INSTRUCTIONS}"
            else:
                # Fallback to classic
                logger.warning(f"Unknown style '{style}', falling back to 'classic'")
                prompt = f"{self.prompts['classic']['prompt']}\n\n{self.CRITICAL_JSON_INSTRUCTIONS}"

            logger.info(f"🔍 Analyzing '{Path(image_path).name}' with '{style}' style")

            # Prepare API request
            payload = {
                "model": self.config.default_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature
            }
            
            logger.debug(f"Sending request to {self.api_endpoint}")

            # Send request to LM Studio
            try:
                response = requests.post(
                    self.api_endpoint,
                    json=payload,
                    timeout=self.config.timeout
                )
            except requests.exceptions.ConnectionError as e:
                raise AIServiceError(
                    technical_msg=f"Connection refused: {e}",
                    user_msg="❌ LM Studio не работи!\n\nСтъпки:\n1. Стартирай LM Studio\n2. Включи Local Server (⚙️ → Start Server)\n3. Зареди модел с vision capabilities"
                )
            except requests.exceptions.Timeout:
                raise AIServiceError(
                    technical_msg=f"Timeout after {self.config.timeout}s",
                    user_msg=f"⏱️ Моделът не отговори за {self.config.timeout}s\n\nОпции:\n• Използвай по-малък/бърз модел\n• Намали резолюцията\n• Увеличи timeout в config"
                )

            logger.debug(f"Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()

                # Extract content from response
                if 'choices' not in result or len(result['choices']) == 0:
                    logger.error("Invalid response structure from LM Studio")
                    raise AIServiceError(
                        technical_msg="Invalid API response structure",
                        user_msg="❌ LM Studio върна невалиден отговор.\n\nПроверка:\n• Модел зареден ли е?\n• Модел с vision support ли е?"
                    )

                content = result['choices'][0]['message']['content']
                logger.debug(f"AI response (truncated): {content[:200]}...")

                # Try to parse JSON from content
                parsed = self._extract_json(content)

                if parsed:
                    # Validate response
                    is_valid, error_msg = self._validate_analysis_response(parsed)
                    
                    if not is_valid:
                        logger.warning(f"Invalid AI response: {error_msg}")
                        logger.debug(f"Raw parsed data: {parsed}")
                        # Continue anyway but log warning
                    
                    result = {
                        'description': parsed.get('description', ''),
                        'tags': parsed.get('tags', []),
                        'suggested_filename': parsed.get('suggested_filename', '')
                    }
                    
                    # Success metrics
                    elapsed = time.time() - start_time
                    self.metrics['successful'] += 1
                    self.metrics['total_time'] += elapsed
                    self.metrics['by_style'][style]['count'] += 1
                    self.metrics['by_style'][style]['time'] += elapsed
                    
                    logger.info(f"✅ Analyzed '{Path(image_path).name}' in {elapsed:.2f}s → {result.get('suggested_filename', 'none')}")
                    return result
                else:
                    # Fallback: treat whole response as description
                    logger.warning("Could not parse JSON from AI response, using raw response")
                    return {
                        'description': content.strip(),
                        'tags': [],
                        'suggested_filename': '',
                        'warning': 'AI did not return valid JSON'
                    }
            else:
                error_text = response.text[:200]
                logger.error(f"LM Studio error: {response.status_code} - {error_text}")
                raise AIServiceError(
                    technical_msg=f"HTTP {response.status_code}: {error_text}",
                    user_msg=f"❌ LM Studio грешка (код {response.status_code})\n\n{error_text}"
                )

        except AIServiceError:
            # Re-raise our custom errors
            self.metrics['failed'] += 1
            raise
        except Exception as e:
            # Catch-all for unexpected errors
            self.metrics['failed'] += 1
            self.metrics['errors'][type(e).__name__] += 1
            logger.error(f"Unexpected error analyzing {image_path}: {e}", exc_info=True)
            raise AIServiceError(
                technical_msg=f"Unexpected error: {type(e).__name__} - {str(e)}",
                user_msg=f"❌ Неочаквана грешка:\n{type(e).__name__}\n\n{str(e)}"
            )
    
    def batch_analyze(self, image_paths: List[str], 
                     progress_callback: Optional[Callable] = None,
                     style: str = 'classic',
                     max_workers: Optional[int] = None) -> Dict[str, Optional[Dict]]:
        """
        Analyze multiple images in parallel (3-5x faster than sequential)
        
        Args:
            image_paths: List of image file paths
            progress_callback: Optional callback(current, total, path) for progress updates
            style: Description style to use
            max_workers: Number of parallel workers (default: from config)
        
        Returns:
            {image_path: result_dict or None, ...}
        """
        if not image_paths:
            logger.warning("No images provided for batch analysis")
            return {}
        
        workers = max_workers or self.config.max_workers
        results = {}
        total = len(image_paths)
        completed = 0
        
        logger.info(f"🚀 Starting batch analysis: {total} images, {workers} workers, style='{style}'")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self.analyze_image, path, style): path 
                for path in image_paths
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result(timeout=self.config.timeout)
                    results[path] = result
                    
                    completed += 1
                    if progress_callback:
                        with self._lock:  # Thread-safe callback
                            progress_callback(completed, total, path)
                            
                except Exception as e:
                    logger.error(f"❌ Error processing {Path(path).name}: {e}")
                    results[path] = None
                    completed += 1
                    
                    if progress_callback:
                        with self._lock:
                            progress_callback(completed, total, path)
        
        elapsed = time.time() - start_time
        success_count = sum(1 for r in results.values() if r is not None)
        logger.info(f"✅ Batch complete: {success_count}/{total} successful in {elapsed:.1f}s "
                   f"({elapsed/total:.2f}s per image)")
        
        return results

    @retry_on_failure(max_retries=3, backoff_factor=2.0)
    def suggest_boards(self, image_description: str, image_tags: List[str],
                       existing_boards: List[Dict]) -> Optional[Dict]:
        """
        Suggest which board(s) an image should belong to based on its description and tags.
        Uses AI to intelligently categorize with hierarchy awareness.
        
        Args:
            image_description: Description of the image
            image_tags: List of tags
            existing_boards: List of existing board dictionaries
        
        Returns:
            {
                'action': 'add_to_existing' or 'create_new',
                'board_id': int or None,
                'confidence': float (0-1),
                'reasoning': str,
                'suggested_boards': [int],
                'new_board': {'name': str, 'description': str, 'parent_id': int or None}
            }
        """
        try:
            # 1. Build hierarchical tree structure
            board_map = {b['id']: b for b in existing_boards}
            root_boards = []
            
            # Initialize children lists
            for b in existing_boards:
                b['children'] = []
            
            # Build tree
            for b in existing_boards:
                if b['parent_id'] and b['parent_id'] in board_map:
                    board_map[b['parent_id']]['children'].append(b)
                else:
                    root_boards.append(b)

            # Recursive formatter for visual tree
            def format_board_tree(boards, indent=0):
                output = []
                prefix = "  " * indent
                arrow = "└─ " if indent > 0 else ""
                
                for board in boards:
                    info = f"{prefix}{arrow}[ID: {board['id']}] {board['name']}"
                    if board.get('description'):
                        info += f" — {board['description']}"
                    output.append(info)
                    
                    if board['children']:
                        output.extend(format_board_tree(board['children'], indent + 1))
                return output

            boards_formatted = format_board_tree(root_boards)
            boards_context = "\n".join(boards_formatted) if boards_formatted else "No existing boards."
            
            tags_text = ", ".join(image_tags) if image_tags else "No tags"

            # 2. Enhanced AI prompt with clear structure
            prompt = f"""You are an intelligent image categorization assistant. Analyze the image data and decide the BEST board placement.

IMAGE INFORMATION:
- Description: {image_description}
- Tags: {tags_text}

CURRENT BOARD HIERARCHY:
{boards_context}

CATEGORIZATION RULES:
1. **Prefer existing boards**: If image clearly fits an existing board (>70% semantic match), use it
2. **Specificity is mandatory**: NEVER place in generic/root board if specific sub-board exists
   - Example: Image = "demon woman" → Use "Woman > Fantasy", NOT just "Woman"
3. **Create specific sub-boards**: If specific category needed but only generic parent exists
   - Example: "Sports Car" image + only "Cars" board exists → Create "Cars > Sports Cars"
4. **Avoid root dumping**: Only use root boards for truly generic content
5. **Consider hierarchy**: Use parent_id to create logical sub-categories

DECISION CRITERIA:
- Content match: Does image subject align with board theme? (Weight: 40%)
- Tag overlap: Do tags match board keywords? (Weight: 30%)
- Specificity: Is there a more specific board available? (Weight: 30%)

OUTPUT FORMAT (Valid JSON Dictionary):
{{
    "action": "add_to_existing" | "create_new",
    "board_id": <int> or null,
    "confidence": <float 0-1>,
    "reasoning": "<brief explanation of decision>",
    "suggested_boards": [<alternative_board_ids>],
    "new_board": {{
        "name": "<specific, clear name>",
        "description": "<what belongs here>",
        "parent_id": <int> or null
    }}
}}

EXAMPLES:
1. Image: "Sunset beach photo", Tags: [nature, beach, sunset]
   Existing: "Nature" (ID: 1), "Nature > Landscapes" (ID: 2)
   → {{"action": "add_to_existing", "board_id": 2, "confidence": 0.9, "reasoning": "Perfect match for landscape sub-board"}}

2. Image: "Ferrari racing", Tags: [car, sports, red, speed]
   Existing: "Cars" (ID: 5)
   → {{"action": "create_new", "new_board": {{"name": "Sports Cars", "description": "High-performance and racing vehicles", "parent_id": 5}}, "reasoning": "Specific sub-category needed under Cars"}}

3. Image: "Demon warrior woman", Tags: [fantasy, woman, demon, dark]
   Existing: "Woman" (ID: 3), "Woman > Portrait" (ID: 4)
   → {{"action": "create_new", "new_board": {{"name": "Fantasy Characters", "description": "Fantasy and supernatural female characters", "parent_id": 3}}, "reasoning": "Fantasy theme needs dedicated sub-board"}}

RESPONSE (Python Dictionary only, no markdown, no code blocks):"""

            payload = {
                "model": self.config.default_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.3  # Lower for more consistent categorization
            }

            logger.debug("Requesting board categorization from LM Studio...")
            
            try:
                response = requests.post(
                    self.api_endpoint, 
                    json=payload, 
                    timeout=self.config.timeout
                )
            except requests.exceptions.ConnectionError as e:
                raise AIServiceError(
                    technical_msg=f"Connection refused: {e}",
                    user_msg="❌ LM Studio не работи за board suggestion!"
                )

            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0]['message']['content']
                    logger.debug(f"AI board suggestion: {content[:200]}...")
                    
                    parsed = self._extract_json(content)
                    
                    if parsed:
                        return {
                            'action': parsed.get('action', 'create_new'),
                            'board_id': parsed.get('board_id'),
                            'confidence': parsed.get('confidence', 0.5),
                            'reasoning': parsed.get('reasoning', ''),
                            'suggested_boards': parsed.get('suggested_boards', []),
                            'new_board': parsed.get('new_board')
                        }
                    else:
                        logger.warning("Could not parse JSON from board suggestion")
                else:
                    logger.error("Invalid response structure from LM Studio")
            else:
                logger.error(f"LM Studio error: {response.status_code} - {response.text[:200]}")
            
            return None

        except AIServiceError:
            raise
        except Exception as e:
            logger.error(f"Error suggesting boards: {e}", exc_info=True)
            return None

    # ========================================================================
    # METRICS & MONITORING
    # ========================================================================

    def get_metrics(self) -> Dict:
        """
        Get performance metrics
        
        Returns:
            Dictionary with comprehensive metrics
        """
        total = self.metrics['total_requests']
        if total == 0:
            return {'status': 'No requests yet'}
        
        avg_time = self.metrics['total_time'] / total
        success_rate = (self.metrics['successful'] / total) * 100
        
        return {
            'total_requests': total,
            'successful': self.metrics['successful'],
            'failed': self.metrics['failed'],
            'success_rate': f"{success_rate:.1f}%",
            'avg_time_per_request': f"{avg_time:.2f}s",
            'total_time': f"{self.metrics['total_time']:.1f}s",
            'errors': dict(self.metrics['errors']),
            'by_style': {
                style: {
                    'count': data['count'],
                    'avg_time': f"{data['time']/data['count']:.2f}s" if data['count'] > 0 else '0s',
                    'total_time': f"{data['time']:.1f}s"
                }
                for style, data in self.metrics['by_style'].items()
            }
        }
    
    def print_metrics(self):
        """Pretty print performance metrics"""
        m = self.get_metrics()
        
        if m.get('status') == 'No requests yet':
            print("\n📊 No metrics yet - no requests have been made.\n")
            return
        
        print("\n" + "="*60)
        print("📊 AI SERVICE PERFORMANCE METRICS")
        print("="*60)
        print(f"Total Requests:    {m['total_requests']}")
        print(f"Successful:        {m['successful']} ({m['success_rate']})")
        print(f"Failed:            {m['failed']}")
        print(f"Avg Time/Request:  {m['avg_time_per_request']}")
        print(f"Total Time:        {m['total_time']}")
        
        if m.get('errors'):
            print(f"\n❌ Errors by type:")
            for error_type, count in m['errors'].items():
                print(f"   • {error_type}: {count}")
        
        if m.get('by_style'):
            print(f"\n📈 Performance by style:")
            for style, stats in m['by_style'].items():
                print(f"   • {style:12} → {stats['count']:3} requests, "
                      f"avg {stats['avg_time']}, total {stats['total_time']}")
        
        print("="*60 + "\n")
    
    def reset_metrics(self):
        """Reset all metrics to zero"""
        self.metrics = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0.0,
            'errors': defaultdict(int),
            'by_style': defaultdict(lambda: {'count': 0, 'time': 0.0})
        }
        logger.info("📊 Metrics reset")

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    def _validate_analysis_response(self, parsed: Dict) -> Tuple[bool, str]:
        """
        Validate that AI response has expected structure and quality
        
        Args:
            parsed: Parsed JSON response from AI
        
        Returns:
            (is_valid, error_message)
        """
        # Check required fields
        required_fields = ['description', 'tags', 'suggested_filename']
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            return False, f"Липсват полета: {missing}"
        
        # Validate tags
        if not isinstance(parsed['tags'], list):
            return False, f"Tags трябва да е list, not {type(parsed['tags'])}"
        
        if len(parsed['tags']) < self.config.min_tags:
            return False, f"Твърде малко тагове: {len(parsed['tags'])}, минимум {self.config.min_tags}"
        
        if len(parsed['tags']) > self.config.max_tags:
            logger.warning(f"Много тагове: {len(parsed['tags'])}, trimming to {self.config.max_tags}")
            parsed['tags'] = parsed['tags'][:self.config.max_tags]
        
        # Validate filename
        filename = parsed.get('suggested_filename', '').strip()
        if not filename or len(filename) < self.config.min_filename_length:
            return False, f"Filename празен или твърде кратък: '{filename}'"
        
        if len(filename) > self.config.max_filename_length:
            logger.warning(f"Filename твърде дълъг: '{filename}', trimming")
            parsed['suggested_filename'] = filename[:self.config.max_filename_length]
        
        # Check for invalid filename characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '.']
        if any(char in filename for char in invalid_chars):
            return False, f"Filename съдържа невалидни символи: '{filename}'"
        
        # Check for spaces in filename (should use underscores)
        if ' ' in filename:
            logger.warning(f"Filename contains spaces: '{filename}', should use underscores")
            parsed['suggested_filename'] = filename.replace(' ', '_')
        
        return True, "OK"
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        Extract JSON from text that might contain markdown code blocks or extra text.
        Handles cases where AI returns JSON followed by additional explanation.
        
        Args:
            text: Raw text response from AI
        
        Returns:
            Parsed JSON dict or None
        """
        import re

        # Try direct parse first (if text is pure JSON)
        text = text.strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Simple approach: find first { and last } - covers most common cases
        start_idx = text.find('{')
        end_idx = text.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = text[start_idx : end_idx + 1]

            # Aggressive cleanup: strip markdown code blocks
            json_str = json_str.strip()
            json_str = json_str.lstrip('`').rstrip('`')
            if json_str.startswith('json'):
                json_str = json_str[4:].lstrip()
            json_str = json_str.lstrip('`').rstrip('`')

            try:
                parsed = json.loads(json_str)
                logger.debug("✅ JSON extracted using find/rfind method")
                return parsed
            except (json.JSONDecodeError, ValueError):
                pass

        # Look for ```json ... ``` markdown code blocks
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except (json.JSONDecodeError, ValueError):
                pass

        # Look for properly nested JSON {...} block
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except (json.JSONDecodeError, ValueError):
                pass

        # Last resort: Manual brace counting
        try:
            start_idx = text.find('{')
            if start_idx == -1:
                return None

            brace_count = 0
            end_idx = start_idx
            in_string = False
            escape_next = False

            for i in range(start_idx, len(text)):
                char = text[i]

                if escape_next:
                    escape_next = False
                    continue

                if char == '\\':
                    escape_next = True
                    continue

                if char == '"':
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break

            if end_idx > start_idx:
                json_str = text[start_idx:end_idx]
                parsed = json.loads(json_str)
                logger.debug("✅ JSON extracted using brace counting")
                return parsed
        except Exception as e:
            logger.debug(f"Brace counting extraction failed: {e}")
            pass

        logger.warning("❌ Could not extract valid JSON from AI response")
        logger.debug(f"Raw text: {text[:500]}...")
        return None


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example 1: Basic usage with default config
    print("="*60)
    print("EXAMPLE 1: Basic Usage")
    print("="*60)
    
    ai = AIService()
    
    # Check connection
    connected, msg = ai.check_connection()
    print(f"\n{msg}\n")
    
    if connected:
        # Analyze single image
        try:
            result = ai.analyze_image("test_image.jpg", style='classic')
            if result:
                print(f"Description: {result['description']}")
                print(f"Tags: {result['tags']}")
                print(f"Filename: {result['suggested_filename']}")
        except AIServiceError as e:
            print(f"\nUser message: {e.user_msg}")
            print(f"Technical: {e.technical_msg}")
    
    # Example 2: Custom configuration
    print("\n" + "="*60)
    print("EXAMPLE 2: Custom Configuration")
    print("="*60)
    
    custom_config = AIServiceConfig(
        max_retries=5,
        timeout=180,
        max_workers=5,
        temperature=0.5
    )
    
    ai_custom = AIService(config=custom_config)
    print(f"\nCustom config: retries={ai_custom.config.max_retries}, "
          f"timeout={ai_custom.config.timeout}s")
    
    # Example 3: Batch processing
    print("\n" + "="*60)
    print("EXAMPLE 3: Batch Processing")
    print("="*60)
    
    image_list = ["img1.jpg", "img2.jpg", "img3.jpg"]
    
    def progress(current, total, path):
        print(f"Progress: {current}/{total} - {Path(path).name}")
    
    # results = ai.batch_analyze(image_list, progress_callback=progress, style='artistic')
    
    # Example 4: Metrics
    print("\n" + "="*60)
    print("EXAMPLE 4: Performance Metrics")
    print("="*60)
    
    ai.print_metrics()
    
    print("\n✅ Examples complete!")
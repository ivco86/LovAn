"""
AI Analysis - analyze images/videos with AI, batch processing
"""

import os
from pathlib import Path
from flask import jsonify, request
from werkzeug.utils import secure_filename

from shared import db, ai, PHOTOS_DIR, DATA_DIR
from utils import get_full_filepath, get_image_for_analysis
from embeddings_utils import generate_embedding_for_image, embedding_to_blob, get_clip_model_version
from . import images_bp


@images_bp.route('/api/images/<int:image_id>/analyze', methods=['POST'])
def analyze_image(image_id):
    """Analyze single image/video with AI and optionally auto-rename and auto-categorize"""
    temp_image_path = None
    try:
        image = db.get_image(image_id)

        if not image:
            return jsonify({'error': 'Image not found'}), 404

        filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)
        media_type = image.get('media_type', 'image')

        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found on disk'}), 404

        # Check AI connection
        connected, message = ai.check_connection()
        if not connected:
            return jsonify({'error': f'AI not available: {message}'}), 503

        # Get style and custom prompt from request
        data = request.get_json() or {}
        style = data.get('style', 'classic')
        custom_prompt = data.get('custom_prompt', None)

        # For videos, extract frame first
        analysis_path = filepath
        if media_type == 'video':
            print(f"[ANALYZE] Extracting frame from video {image_id} for AI analysis...")

            # Get frame as PIL Image
            frame_img = get_image_for_analysis(filepath, media_type='video')

            if not frame_img:
                return jsonify({'error': 'Could not extract frame from video for analysis'}), 500

            # Save frame to temporary file
            temp_dir = os.path.join(DATA_DIR, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            temp_image_path = os.path.join(temp_dir, f"video_frame_{image_id}.jpg")
            frame_img.save(temp_image_path, 'JPEG', quality=95)
            analysis_path = temp_image_path

            print(f"[ANALYZE] Video frame extracted to {temp_image_path}")

        # Analyze image with specified style
        print(f"[ANALYZE] Analyzing image {image_id} with style '{style}'...")
        result = ai.analyze_image(analysis_path, style=style, custom_prompt=custom_prompt)

        if result:
            print(f"[ANALYZE] AI analysis complete for image {image_id}")
            print(f"[ANALYZE] Description: {result['description'][:100]}...")
            print(f"[ANALYZE] Tags: {result['tags']}")

            # Update database with analysis
            print(f"[ANALYZE] Updating database for image {image_id}...")
            db.update_image_analysis(
                image_id,
                result['description'],
                result['tags']
            )
            print(f"[ANALYZE] ✅ Database updated successfully for image {image_id}")

            # --- 1. SMART BOARDS (Съществуващи правила) ---
            added_to_boards = []
            try:
                added_to_boards = db.process_smart_boards(image_id)
                if added_to_boards:
                    print(f"[ANALYZE] 🤖 Auto-categorized image {image_id} into {len(added_to_boards)} smart board(s)")
            except Exception as e:
                print(f"[ANALYZE] ⚠️ Smart boards processing failed: {e}")

            # --- 2. AUTO SUGGEST & CREATE (Ако не е добавена никъде) ---
            if not added_to_boards:
                try:
                    print(f"[ANALYZE] 🤔 Image not in any board, asking AI for suggestions...")
                    all_boards = db.get_all_boards()
                    
                    # Викаме AI да предложи структура
                    suggestion = ai.suggest_boards(
                        result['description'], 
                        result['tags'], 
                        all_boards
                    )
                    
                    if suggestion:
                        # Случай А: AI предлага да създадем НОВ БОРД
                        if suggestion['action'] == 'create_new' and suggestion.get('new_board'):
                            new_data = suggestion['new_board']
                            print(f"[ANALYZE] 💡 AI suggests creating NEW board: '{new_data['name']}'")
                            
                            # Създаваме борда
                            new_board_id = db.create_board(
                                name=new_data['name'],
                                description=new_data.get('description'),
                                parent_id=new_data.get('parent_id')
                            )
                            
                            # Добавяме снимката в новия борд
                            db.add_image_to_board(new_board_id, image_id)
                            print(f"[ANALYZE] ✨ Created board '{new_data['name']}' and added image {image_id}")
                            
                        # Случай Б: AI е открил съществуващ борд, който Smart Rules са пропуснали
                        elif suggestion['action'] == 'add_to_existing':
                            for b_id in suggestion['suggested_boards']:
                                db.add_image_to_board(b_id, image_id)
                                print(f"[ANALYZE] 📎 AI matched image {image_id} to existing board {b_id}")

                except Exception as e:
                    print(f"[ANALYZE] ⚠️ Auto-board suggestion failed: {e}")
            # -------------------------------------------------------

            # --- 3. EMBEDDINGS (CLIP) ---
            try:
                embedding = generate_embedding_for_image(analysis_path)
                if embedding is not None:
                    blob = embedding_to_blob(embedding)
                    model_version = get_clip_model_version() or 'clip-vit-base-patch32'
                    db.save_embedding(image_id, blob, model_version=model_version)
                    print(f"[ANALYZE] ✅ Auto-generated embedding for image {image_id} (model: {model_version})")
                else:
                    print(f"[ANALYZE] ⚠️ Could not generate embedding for image {image_id} (CLIP may not be available)")
            except Exception as e:
                print(f"[ANALYZE] ⚠️ Failed to generate embedding: {e}")
            # ----------------------------

            # Auto-rename if AI suggested a filename
            new_filename = None
            renamed = False

            if result.get('suggested_filename'):
                suggested = result['suggested_filename'].strip()

                if suggested and len(suggested) > 0:
                    # Sanitize filename
                    suggested = secure_filename(suggested)

                    # Get original extension
                    old_ext = Path(filepath).suffix

                    # Build new filename
                    new_filename = f"{suggested}{old_ext}"

                    # Get directory
                    directory = os.path.dirname(filepath)
                    new_filepath = os.path.join(directory, new_filename)

                    # Check if different from current name
                    if new_filepath != filepath:
                        # Check if target exists
                        if not os.path.exists(new_filepath):
                            try:
                                # Rename file on disk
                                os.rename(filepath, new_filepath)

                                # Update database
                                db.rename_image(image_id, new_filepath, new_filename)

                                renamed = True
                                print(f"Auto-renamed: {image['filename']} → {new_filename}")
                            except Exception as e:
                                print(f"Auto-rename failed: {e}")
                                renamed = False
                        else:
                            # File exists, add counter
                            counter = 1
                            base_name = suggested
                            while os.path.exists(new_filepath) and counter < 100:
                                new_filename = f"{base_name}_{counter}{old_ext}"
                                new_filepath = os.path.join(directory, new_filename)
                                counter += 1

                            if not os.path.exists(new_filepath):
                                try:
                                    os.rename(filepath, new_filepath)
                                    db.rename_image(image_id, new_filepath, new_filename)
                                    renamed = True
                                    print(f"Auto-renamed: {image['filename']} → {new_filename}")
                                except Exception as e:
                                    print(f"Auto-rename failed: {e}")

            return jsonify({
                'success': True,
                'image_id': image_id,
                'description': result['description'],
                'tags': result['tags'],
                'renamed': renamed,
                'new_filename': new_filename if renamed else image['filename'],
                'suggested_filename': result.get('suggested_filename', '')
            })
        else:
            return jsonify({'error': 'Analysis failed - AI returned no result'}), 500

    except Exception as e:
        print(f"Error analyzing image {image_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Analysis error: {str(e)}'}), 500
    finally:
        # Clean up temporary video frame if created
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
                print(f"[ANALYZE] Cleaned up temporary frame file: {temp_image_path}")
            except Exception as e:
                print(f"[ANALYZE] Warning: Could not delete temp file {temp_image_path}: {e}")


@images_bp.route('/api/analyze-batch', methods=['POST'])
def batch_analyze():
    """Analyze all unanalyzed images with auto-rename"""
    limit = request.args.get('limit', 10, type=int)

    # Check AI connection
    connected, message = ai.check_connection()
    if not connected:
        return jsonify({'error': f'AI not available: {message}'}), 503

    # Get unanalyzed images
    images = db.get_unanalyzed_images(limit=limit)

    if not images:
        return jsonify({
            'success': True,
            'message': 'No unanalyzed images',
            'analyzed': 0
        })

    analyzed_count = 0
    failed_count = 0
    renamed_count = 0

    for image in images:
        filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)
        image_id = image['id']

        if not os.path.exists(filepath):
            failed_count += 1
            continue

        result = ai.analyze_image(filepath)

        if result:
            # Update analysis
            db.update_image_analysis(
                image_id,
                result['description'],
                result['tags']
            )
            analyzed_count += 1

            # --- AUTO CATEGORIZE FOR BATCH ---
            try:
                added = db.process_smart_boards(image_id)
                if not added:
                    # За batch режим, може би искаме само да добавяме към съществуващи,
                    # за да не създаваме 100 нови папки. Но ето логиката и тук:
                    all_b = db.get_all_boards()
                    sugg = ai.suggest_boards(result['description'], result['tags'], all_b)
                    if sugg and sugg['action'] == 'create_new' and sugg.get('new_board'):
                         # Create ONLY if confidence is high (optional logic)
                         pass # В batch режим е по-безопасно да не създаваме нови папки автоматично, за да не стане хаос
                    elif sugg and sugg['action'] == 'add_to_existing':
                         for bid in sugg['suggested_boards']:
                             db.add_image_to_board(bid, image_id)
            except:
                pass
            # --------------------------------

            # Generate Embedding
            try:
                embedding = generate_embedding_for_image(filepath)
                if embedding is not None:
                    blob = embedding_to_blob(embedding)
                    db.save_embedding(image_id, blob)
            except:
                pass

            # Auto-rename if AI suggested a filename
            if result.get('suggested_filename'):
                suggested = result['suggested_filename'].strip()

                if suggested and len(suggested) > 0:
                    # Sanitize filename
                    suggested = secure_filename(suggested)

                    # Get original extension
                    old_ext = Path(filepath).suffix

                    # Build new filename
                    new_filename = f"{suggested}{old_ext}"

                    # Get directory
                    directory = os.path.dirname(filepath)
                    new_filepath = os.path.join(directory, new_filename)

                    # Check if different from current name
                    if new_filepath != filepath:
                        # Check if target exists
                        if not os.path.exists(new_filepath):
                            try:
                                # Rename file on disk
                                os.rename(filepath, new_filepath)

                                # Update database
                                db.rename_image(image_id, new_filepath, new_filename)

                                renamed_count += 1
                                print(f"Batch auto-renamed: {image['filename']} → {new_filename}")
                            except Exception as e:
                                print(f"Batch auto-rename failed for {image['filename']}: {e}")
                        else:
                            # File exists, add counter
                            counter = 1
                            base_name = suggested
                            while os.path.exists(new_filepath) and counter < 100:
                                new_filename = f"{base_name}_{counter}{old_ext}"
                                new_filepath = os.path.join(directory, new_filename)
                                counter += 1

                            if not os.path.exists(new_filepath):
                                try:
                                    os.rename(filepath, new_filepath)
                                    db.rename_image(image_id, new_filepath, new_filename)
                                    renamed_count += 1
                                    print(f"Batch auto-renamed: {image['filename']} → {new_filename}")
                                except Exception as e:
                                    print(f"Batch auto-rename failed for {image['filename']}: {e}")
        else:
            failed_count += 1

    return jsonify({
        'success': True,
        'total': len(images),
        'analyzed': analyzed_count,
        'renamed': renamed_count,
        'failed': failed_count
    })
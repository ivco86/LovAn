"""
CLIP embeddings and semantic search - hybrid text + visual search
"""

import os
from flask import jsonify, request

from shared import db, PHOTOS_DIR
from utils import get_full_filepath
from embeddings_utils import (
    is_clip_available,
    generate_embedding_for_image,
    search_by_text_query,
    find_similar_images,
    embedding_to_blob,
    blob_to_embedding,
    get_clip_model_version
)
from . import ai_bp


@ai_bp.route('/api/embeddings/status', methods=['GET'])
def embeddings_status():
    """Get CLIP embeddings status and coverage"""
    clip_available = is_clip_available()
    total_images = db.get_stats()['total_images']
    embeddings_count = db.count_embeddings()
    
    return jsonify({
        'clip_available': clip_available,
        'total_images': total_images,
        'embeddings_count': embeddings_count,
        'coverage_percent': round((embeddings_count / total_images * 100) if total_images > 0 else 0, 1),
        'message': 'CLIP model ready' if clip_available else 'Install transformers and torch'
    })


@ai_bp.route('/api/embeddings/generate', methods=['POST'])
def generate_embeddings():
    """Generate CLIP embeddings for images without them"""
    if not is_clip_available():
        return jsonify({'error': 'CLIP not available'}), 503

    limit = request.args.get('limit', 100, type=int)
    images = db.get_images_without_embeddings(limit=limit)

    if not images:
        return jsonify({
            'success': True,
            'message': 'All images have embeddings',
            'generated': 0
        })

    generated, failed = 0, 0
    for image in images:
        filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)
        if not os.path.exists(filepath):
            failed += 1
            continue
            
        embedding = generate_embedding_for_image(filepath)
        if embedding is not None:
            embedding_blob = embedding_to_blob(embedding)
            model_version = get_clip_model_version() or 'unknown'
            if db.save_embedding(image['id'], embedding_blob, model_version=model_version):
                generated += 1
                print(f"Generated embedding for {image['id']}")
            else:
                failed += 1
        else:
            failed += 1

    return jsonify({
        'success': True,
        'generated': generated,
        'failed': failed
    })


@ai_bp.route('/api/search/semantic', methods=['POST'])
def semantic_search():
    """
    HYBRID SEARCH: Combines Text Search (Tags/Desc) + Semantic Search (CLIP)
    This gives the best of both worlds.
    """
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 20)

    if not query:
        return jsonify({'error': 'Query required'}), 400
    
    final_results = {}  # Map image_id -> result_object

    # 1. KEYWORD SEARCH (The "Classic" Exact Match)
    try:
        text_matches = db.search_images(query, limit=top_k)
        print(f"[HYBRID] Text search found: {len(text_matches)} matches")
        
        for img in text_matches:
            img_id = img['id']
            # Give high bonus for text match
            final_results[img_id] = {
                **img,
                'similarity': 0.5,  # Base high score for text match
                'score_display': 'Text Match'
            }
    except Exception as e:
        print(f"[HYBRID] Text search error: {e}")

    # 2. SEMANTIC SEARCH (The "Vibe" Match)
    if is_clip_available():
        all_embeddings = db.get_all_embeddings()
        if all_embeddings:
            # Prepare valid embeddings
            valid_embeddings = []
            for item in all_embeddings:
                try:
                    emb_array = blob_to_embedding(item['embedding'])
                    if emb_array is not None:
                        item['embedding'] = emb_array
                        valid_embeddings.append(item)
                except Exception as e:
                    print(f"[HYBRID] Error processing embedding for image {item.get('id', 'unknown')}: {e}")
                    continue
            
            if valid_embeddings:
                try:
                    clip_results = search_by_text_query(query, valid_embeddings)
                    
                    if clip_results:
                        print(f"[HYBRID] CLIP search found: {len(clip_results)} raw matches")
                        
                        for res in clip_results:
                            img_id = res['image_id']
                            score = res['similarity']
                            
                            # FILTER: Ignore weak CLIP results
                            if score < 0.21:
                                continue
                            
                            # If already in results from text search, boost the score!
                            if img_id in final_results:
                                final_results[img_id]['similarity'] += score  # Boost!
                                pct = min(int(final_results[img_id]['similarity'] * 100), 99)
                                final_results[img_id]['score_display'] = f"{pct}% (Hybrid)"
                            else:
                                # Add if it's a strong CLIP result
                                image = db.get_image(img_id)
                                if image:
                                    pct = min(int(score * 300), 99)
                                    final_results[img_id] = {
                                        **image,
                                        'similarity': score,
                                        'score_display': f"{pct}% (AI)"
                                    }
                except Exception as e:
                    print(f"[HYBRID] CLIP search error: {e}")
                    import traceback
                    traceback.print_exc()

    # 3. SORT & RETURN
    sorted_images = sorted(final_results.values(), key=lambda x: x['similarity'], reverse=True)
    top_results = sorted_images[:top_k]
    
    print(f"[HYBRID] Final combined results: {len(top_results)}")

    return jsonify({
        'query': query,
        'results': top_results,
        'count': len(top_results)
    })


@ai_bp.route('/api/images/<int:image_id>/similar', methods=['GET'])
def get_similar_images_by_embedding(image_id):
    """Find similar images using CLIP embeddings"""
    if not is_clip_available():
        return jsonify({'error': 'CLIP not available'}), 503

    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    query_blob = db.get_embedding(image_id)
    if not query_blob:
        return jsonify({'error': 'No embedding'}), 404
    
    query_emb = blob_to_embedding(query_blob)
    if query_emb is None:
        return jsonify({'error': 'Failed to decode embedding'}), 500
    
    all_embeddings = db.get_all_embeddings()
    
    # Prepare valid embeddings
    valid_embeddings = []
    for item in all_embeddings:
        try:
            emb = blob_to_embedding(item['embedding'])
            if emb is not None and hasattr(emb, 'shape') and hasattr(query_emb, 'shape') and emb.shape == query_emb.shape:
                item['embedding'] = emb
                valid_embeddings.append(item)
        except Exception:
            continue

    top_k = request.args.get('top_k', 20, type=int)
    similar = find_similar_images(query_emb, valid_embeddings, top_k=top_k, exclude_id=image_id)

    images = []
    for res in similar:
        if res['similarity'] > 0.22:
            img = db.get_image(res['image_id'])
            if img:
                pct = min(int(res['similarity'] * 100), 99)
                images.append({
                    **img,
                    'similarity': round(res['similarity'], 3),
                    'score_display': f"{pct}% match"
                })

    return jsonify({
        'image_id': image_id,
        'similar': images,
        'count': len(images)
    })

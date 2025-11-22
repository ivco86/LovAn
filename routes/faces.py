"""
Face recognition API routes
"""

from flask import Blueprint, jsonify, request
from database import Database
from face_recognition_service import FaceRecognitionService
import numpy as np

faces_bp = Blueprint('faces', __name__)
db = Database()
face_service = FaceRecognitionService(model_name='Facenet', detector_backend='opencv')


@faces_bp.route('/api/faces/detect/<int:image_id>', methods=['POST'])
def detect_faces_in_image(image_id):
    """Detect faces in a specific image"""
    try:
        image = db.get_image(image_id)
        if not image:
            return jsonify({'error': 'Image not found'}), 404

        if not face_service.enabled:
            return jsonify({'error': 'Face recognition not available. Install DeepFace first.'}), 503

        # Detect faces
        faces = face_service.detect_and_analyze_faces(image['filepath'])

        # Save to database
        saved_faces = []
        for face_data in faces:
            # Add face to database
            face_id = db.add_face(
                image_id=image_id,
                bounding_box=face_data['bounding_box'],
                confidence=face_data.get('confidence', 1.0),
                age=face_data.get('age'),
                gender=face_data.get('gender'),
                emotion=face_data.get('emotion')
            )

            if face_id and face_data.get('embedding') is not None:
                # Store embedding
                embedding_bytes = face_service.serialize_embedding(face_data['embedding'])
                db.add_face_embedding(face_id, embedding_bytes, face_service.model_name)

            saved_faces.append({
                'face_id': face_id,
                'bounding_box': face_data['bounding_box'],
                'age': face_data.get('age'),
                'gender': face_data.get('gender'),
                'emotion': face_data.get('emotion')
            })

        return jsonify({
            'success': True,
            'image_id': image_id,
            'faces_detected': len(saved_faces),
            'faces': saved_faces
        })

    except Exception as e:
        print(f"[FACES API] Error detecting faces: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/faces/image/<int:image_id>', methods=['GET'])
def get_faces_for_image(image_id):
    """Get all faces detected in an image"""
    try:
        faces = db.get_faces_by_image(image_id)
        return jsonify({
            'success': True,
            'image_id': image_id,
            'faces': faces
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/people', methods=['GET'])
def get_all_people():
    """Get all person groups"""
    try:
        people = db.get_all_person_groups()
        return jsonify({
            'success': True,
            'people': people
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/people/<int:person_id>', methods=['GET'])
def get_person(person_id):
    """Get person details with their faces"""
    try:
        person = db.get_person_group(person_id)
        if not person:
            return jsonify({'error': 'Person not found'}), 404

        faces = db.get_faces_by_person(person_id, limit=100)

        return jsonify({
            'success': True,
            'person': person,
            'faces': faces
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/people', methods=['POST'])
def create_person():
    """Create a new person group"""
    try:
        data = request.json or {}
        name = data.get('name')

        person_id = db.create_person_group(name)

        return jsonify({
            'success': True,
            'person_id': person_id,
            'name': name
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/people/<int:person_id>', methods=['PUT', 'PATCH'])
def update_person(person_id):
    """Update person name"""
    try:
        data = request.json or {}
        name = data.get('name')

        if not name:
            return jsonify({'error': 'Name is required'}), 400

        success = db.update_person_group_name(person_id, name)

        if success:
            return jsonify({
                'success': True,
                'person_id': person_id,
                'name': name
            })
        else:
            return jsonify({'error': 'Failed to update person'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/people/<int:person_id>', methods=['DELETE'])
def delete_person(person_id):
    """Delete a person group"""
    try:
        success = db.delete_person_group(person_id)

        if success:
            return jsonify({
                'success': True,
                'person_id': person_id
            })
        else:
            return jsonify({'error': 'Failed to delete person'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/faces/<int:face_id>/assign', methods=['POST'])
def assign_face_to_person(face_id):
    """Assign a face to a person group"""
    try:
        data = request.json or {}
        person_group_id = data.get('person_group_id') or data.get('person_id')

        if not person_group_id:
            return jsonify({'error': 'person_group_id is required'}), 400

        success = db.assign_face_to_person(face_id, person_group_id)

        if success:
            return jsonify({
                'success': True,
                'face_id': face_id,
                'person_id': person_group_id
            })
        else:
            return jsonify({'error': 'Failed to assign face'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/faces/<int:face_id>/unassign', methods=['POST'])
def unassign_face_from_person(face_id):
    """Remove a face from its person group (make it unassigned)"""
    try:
        # Set person_group_id to NULL
        success = db.unassign_face(face_id)

        if success:
            return jsonify({
                'success': True,
                'face_id': face_id
            })
        else:
            return jsonify({'error': 'Failed to unassign face'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/faces/unassigned', methods=['GET'])
def get_unassigned_faces():
    """Get faces that haven't been assigned to any person"""
    try:
        faces = db.get_unassigned_faces(limit=200)
        return jsonify({
            'success': True,
            'faces': faces
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/faces/cluster', methods=['POST'])
def cluster_all_faces():
    """
    Auto-cluster all unassigned faces into person groups
    Uses similarity threshold to group similar faces
    """
    try:
        data = request.json or {}
        similarity_threshold = data.get('similarity_threshold', 0.6)

        # Get all face embeddings
        face_embeddings_raw = db.get_all_face_embeddings()

        # Filter only unassigned faces
        unassigned_embeddings = []
        for face_id, embedding_bytes, person_group_id in face_embeddings_raw:
            if person_group_id is None:
                embedding = face_service.deserialize_embedding(embedding_bytes)
                if embedding is not None:
                    unassigned_embeddings.append((face_id, embedding))

        if not unassigned_embeddings:
            return jsonify({
                'success': True,
                'message': 'No unassigned faces to cluster',
                'groups_created': 0
            })

        # Cluster faces
        face_to_group = face_service.cluster_faces(unassigned_embeddings, similarity_threshold)

        # Create person groups and assign faces
        group_id_map = {}  # cluster_label -> person_group_id
        groups_created = 0

        for face_id, cluster_label in face_to_group.items():
            if cluster_label not in group_id_map:
                # Create new person group
                person_id = db.create_person_group(name=None)
                group_id_map[cluster_label] = person_id
                groups_created += 1

            # Assign face to person group
            person_id = group_id_map[cluster_label]
            db.assign_face_to_person(face_id, person_id)

        return jsonify({
            'success': True,
            'faces_clustered': len(face_to_group),
            'groups_created': groups_created
        })

    except Exception as e:
        print(f"[FACES API] Error clustering faces: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@faces_bp.route('/api/faces/status', methods=['GET'])
def get_face_recognition_status():
    """Get face recognition service status"""
    return jsonify({
        'enabled': face_service.enabled,
        'model': face_service.model_name if face_service.enabled else None,
        'detector': face_service.detector_backend if face_service.enabled else None
    })
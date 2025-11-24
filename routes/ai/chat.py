"""
AI Chat route - Direct conversation with AI
Allows users to chat with the AI model through LM Studio
"""

from flask import request, jsonify
import requests
import logging
from . import ai_bp
from shared import LM_STUDIO_URL

logger = logging.getLogger(__name__)


@ai_bp.route('/api/ai/chat', methods=['POST'])
def chat():
    """
    Chat with AI model

    Request body:
    {
        "message": "User message",
        "history": [
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"}
        ]
    }

    Returns:
    {
        "response": "AI response",
        "success": true
    }
    """
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        chat_history = data.get('history', [])

        if not user_message:
            return jsonify({
                'success': False,
                'error': 'Message cannot be empty'
            }), 400

        # Build messages array for LM Studio API
        messages = []

        # Add system message
        messages.append({
            "role": "system",
            "content": "You are a helpful AI assistant in an image gallery application. You can help users with questions, provide information, and have friendly conversations. Be concise and helpful."
        })

        # Add chat history
        for msg in chat_history:
            messages.append({
                "role": msg.get('role', 'user'),
                "content": msg.get('content', '')
            })

        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })

        # Call LM Studio API
        logger.info(f"💬 Sending chat message to LM Studio...")

        response = requests.post(
            f"{LM_STUDIO_URL}/v1/chat/completions",
            json={
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
                "stream": False
            },
            timeout=60
        )

        if response.status_code != 200:
            logger.error(f"LM Studio error: {response.status_code} - {response.text}")
            return jsonify({
                'success': False,
                'error': 'AI service is not available. Please check if LM Studio is running.'
            }), 503

        result = response.json()
        ai_response = result['choices'][0]['message']['content']

        logger.info(f"✅ Chat response generated")

        return jsonify({
            'success': True,
            'response': ai_response
        })

    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to LM Studio")
        return jsonify({
            'success': False,
            'error': 'Cannot connect to AI service. Please make sure LM Studio is running on http://localhost:1234'
        }), 503

    except requests.exceptions.Timeout:
        logger.error("❌ LM Studio timeout")
        return jsonify({
            'success': False,
            'error': 'AI service timeout. Please try again.'
        }), 504

    except Exception as e:
        logger.error(f"❌ Chat error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

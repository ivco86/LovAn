/**
 * AI Chat functionality
 * Handles real-time chat with AI assistant
 */

// Chat state
const chatState = {
    history: [],
    isOpen: false,
    isLoading: false
};

// Initialize chat when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initChat();
});

/**
 * Initialize chat functionality
 */
function initChat() {
    const chatBtn = document.getElementById('chatBtn');
    const chatModal = document.getElementById('chatModal');
    const chatClose = document.getElementById('chatClose');
    const chatOverlay = document.getElementById('chatOverlay');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatInput = document.getElementById('chatInput');

    // Open chat modal
    chatBtn.addEventListener('click', () => {
        openChat();
    });

    // Close chat modal
    chatClose.addEventListener('click', () => {
        closeChat();
    });

    chatOverlay.addEventListener('click', () => {
        closeChat();
    });

    // Send message on button click
    chatSendBtn.addEventListener('click', () => {
        sendMessage();
    });

    // Send message on Enter key
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

/**
 * Open chat modal
 */
function openChat() {
    const chatModal = document.getElementById('chatModal');
    chatModal.style.display = 'block';
    chatState.isOpen = true;

    // Focus on input
    setTimeout(() => {
        document.getElementById('chatInput').focus();
    }, 100);
}

/**
 * Close chat modal
 */
function closeChat() {
    const chatModal = document.getElementById('chatModal');
    chatModal.style.display = 'none';
    chatState.isOpen = false;
}

/**
 * Send user message to AI
 */
async function sendMessage() {
    const chatInput = document.getElementById('chatInput');
    const message = chatInput.value.trim();

    if (!message || chatState.isLoading) {
        return;
    }

    // Clear input
    chatInput.value = '';

    // Add user message to chat
    addMessageToChat('user', message);

    // Show loading
    setLoading(true);

    try {
        // Send to API
        const response = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                history: chatState.history
            })
        });

        const data = await response.json();

        if (data.success) {
            // Add AI response to chat
            addMessageToChat('assistant', data.response);

            // Update history
            chatState.history.push(
                { role: 'user', content: message },
                { role: 'assistant', content: data.response }
            );
        } else {
            // Show error
            addMessageToChat('error', data.error || 'Failed to get response from AI');
        }
    } catch (error) {
        console.error('Chat error:', error);
        addMessageToChat('error', 'Failed to connect to AI service. Please try again.');
    } finally {
        setLoading(false);
    }
}

/**
 * Add message to chat UI
 */
function addMessageToChat(role, content) {
    const chatMessages = document.getElementById('chatMessages');

    // Remove welcome message if present
    const welcomeMsg = chatMessages.querySelector('.chat-message-welcome');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // Create message element
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message chat-message-${role}`;

    // Style based on role
    const isUser = role === 'user';
    const isError = role === 'error';

    messageDiv.style.cssText = `
        display: flex;
        justify-content: ${isUser ? 'flex-end' : 'flex-start'};
        margin-bottom: var(--spacing-md);
        animation: slideIn 0.3s ease-out;
    `;

    const messageBubble = document.createElement('div');
    messageBubble.style.cssText = `
        max-width: 70%;
        padding: var(--spacing-sm) var(--spacing-md);
        border-radius: var(--radius-md);
        background: ${isUser ? 'var(--primary)' : isError ? 'var(--danger)' : 'var(--bg-tertiary)'};
        color: ${isUser || isError ? 'white' : 'var(--text-primary)'};
        word-wrap: break-word;
        white-space: pre-wrap;
        line-height: 1.5;
    `;

    // Format content
    messageBubble.textContent = content;

    messageDiv.appendChild(messageBubble);
    chatMessages.appendChild(messageDiv);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Set loading state
 */
function setLoading(loading) {
    chatState.isLoading = loading;
    const chatLoading = document.getElementById('chatLoading');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatInput = document.getElementById('chatInput');

    if (loading) {
        chatLoading.style.display = 'block';
        chatSendBtn.disabled = true;
        chatInput.disabled = true;
    } else {
        chatLoading.style.display = 'none';
        chatSendBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

/**
 * Clear chat history
 */
function clearChat() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = `
        <div class="chat-message-welcome" style="
            text-align: center;
            padding: var(--spacing-xl);
            color: var(--text-muted);
        ">
            <div style="font-size: 3rem; margin-bottom: var(--spacing-md);">👋</div>
            <p>Hi! I'm your AI assistant. How can I help you today?</p>
        </div>
    `;
    chatState.history = [];
}

// Add slide-in animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
`;
document.head.appendChild(style);

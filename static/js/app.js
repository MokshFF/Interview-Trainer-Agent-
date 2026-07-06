const themeToggle = document.getElementById('themeToggle');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const chatWindow = document.getElementById('chatWindow');
const profileForm = document.getElementById('profileForm');
const resumeForm = document.getElementById('resumeForm');
const quickStartPrompts = document.getElementById('quickStartPrompts');
const resumeAttachButton = document.getElementById('resumeAttachButton');
const chatHistoryKey = 'interview_trainer_chat_history';
let chatHistory = [];

function getProfilePayload() {
  const formData = new FormData(profileForm);
  const skills = (formData.get('skills') || '').split(',').map((item) => item.trim()).filter(Boolean);
  return {
    candidate_name: formData.get('candidate_name'),
    target_role: formData.get('target_role'),
    experience_level: formData.get('experience_level'),
    target_company: formData.get('target_company'),
    skills,
  };
}

function formatMarkdown(text) {
  let escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
  
  // Format markdown code blocks: ```lang ... ``` or ``` ... ```
  escaped = escaped.replace(/```(?:[a-zA-Z0-9+#/-]+)?([\s\S]*?)```/g, '<pre class="code-block"><code>$1</code></pre>');
  
  // Format inline code: `code`
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // Replace double asterisks with <strong> tags
  escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  
  // Format markdown tables: parse lines starting and ending with pipe '|'
  const lines = escaped.split('\n');
  let inTable = false;
  let tableHTML = '';
  const processedLines = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableHTML = '<div class="table-responsive"><table class="table table-bordered table-dark-custom"><thead>';
      }
      
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      
      // Check if it's separator row like |---|---|
      if (cells.every(c => /^[-:]+$/.test(c))) {
        // Switch table header to body
        if (tableHTML.includes('<thead>') && !tableHTML.includes('<tbody>')) {
          tableHTML += '</thead><tbody>';
        }
        continue;
      }
      
      // If we haven't closed the header, treat the first row as headers
      const isHeaderRow = tableHTML.includes('<thead>') && !tableHTML.includes('</thead>');
      tableHTML += '<tr>';
      for (const cell of cells) {
        if (isHeaderRow) {
          tableHTML += `<th>${cell}</th>`;
        } else {
          tableHTML += `<td>${cell}</td>`;
        }
      }
      tableHTML += '</tr>';
    } else {
      if (inTable) {
        inTable = false;
        // Make sure table tags are properly closed
        if (tableHTML.includes('<thead>') && !tableHTML.includes('<tbody>')) {
          tableHTML += '</thead><tbody>';
        }
        tableHTML += '</tbody></table></div>';
        processedLines.push(tableHTML);
        tableHTML = '';
      }
      processedLines.push(lines[i]);
    }
  }
  if (inTable) {
    if (tableHTML.includes('<thead>') && !tableHTML.includes('<tbody>')) {
      tableHTML += '</thead><tbody>';
    }
    tableHTML += '</tbody></table></div>';
    processedLines.push(tableHTML);
  }

  escaped = processedLines.join('\n');
  
  // Split by pre blocks to avoid double-newline breaks inside preformatted code
  const parts = escaped.split(/(<pre[\s\S]*?<\/pre>)/g);
  for (let i = 0; i < parts.length; i++) {
    if (!parts[i].startsWith('<pre')) {
      parts[i] = parts[i].replace(/\n/g, '<br>');
    }
  }
  return parts.join('');
}

function appendMessage(text, role) {
  const row = document.createElement('div');
  row.className = `chat-msg-row ${role}`;
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (role === 'assistant') {
    row.innerHTML = `
      <div class="chat-avatar">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8 12c-2.33 0-4.31-1.46-5.11-3.5h10.22c-.8 2.04-2.78 3.5-5.11 3.5zm-3-5.5c-.83 0-1.5-.67-1.5-1.5S8.17 6.5 9 6.5s1.5.67 1.5 1.5S9.83 8.5 9 8.5zm6 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
        </svg>
      </div>
      <div class="chat-msg-content">
        <div class="chat-msg-meta">
          <span class="name">Interview Trainer Agent</span>
          <span class="time">${timeStr}</span>
        </div>
        <div class="chat-msg-bubble"></div>
        <div class="chat-msg-actions">
          <button class="chat-action-btn" title="Like"><i class="fa-regular fa-thumbs-up"></i></button>
          <button class="chat-action-btn" title="Dislike"><i class="fa-regular fa-thumbs-down"></i></button>
          <button class="chat-action-btn" title="Copy"><i class="fa-regular fa-copy"></i></button>
          <button class="chat-action-btn" title="Report bug"><i class="fa-solid fa-bug"></i></button>
        </div>
      </div>
    `;
    row.querySelector('.chat-msg-bubble').innerHTML = formatMarkdown(text);
  } else {
    row.innerHTML = `
      <div class="chat-msg-content">
        <div class="chat-msg-bubble"></div>
      </div>
    `;
    row.querySelector('.chat-msg-bubble').textContent = text;
  }

  chatWindow.appendChild(row);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function loadChatHistory() {
  try {
    const stored = localStorage.getItem(chatHistoryKey);
    chatHistory = stored ? JSON.parse(stored) : [];
  } catch {
    chatHistory = [];
  }
}

function saveChatHistory() {
  localStorage.setItem(chatHistoryKey, JSON.stringify(chatHistory.slice(-20)));
}

function setInitialCoachState() {
  if (!chatWindow || chatWindow.querySelectorAll('.chat-msg-row').length > 0) return;
  appendMessage('Hi! I am your AI Interview Trainer Agent. I generate tailored question sets and preparation strategies based on your profile name, experience level, and job role. Ask me for questions on a topic (like SQL, AI, or DSA) or type "mock test" to start a mock interview!', 'assistant');
}

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') || 'light';
}

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

setTheme(localStorage.getItem('theme') || 'light');
loadChatHistory();
setInitialCoachState();

function sendPrompt(prompt) {
  if (!prompt) return;
  chatInput.value = prompt;
  chatForm.requestSubmit();
}

quickStartPrompts?.addEventListener('click', (event) => {
  const button = event.target.closest('[data-prompt]');
  if (!button) return;
  sendPrompt(button.getAttribute('data-prompt'));
});

resumeAttachButton?.addEventListener('click', () => {
  resumeForm?.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

themeToggle?.addEventListener('click', () => {
  setTheme(currentTheme() === 'light' ? 'dark' : 'light');
});

// Typing Indicator helpers
function showTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'chat-msg-row assistant typing-row';
  row.id = 'chatTypingIndicator';
  row.innerHTML = `
    <div class="chat-avatar">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8 12c-2.33 0-4.31-1.46-5.11-3.5h10.22c-.8 2.04-2.78 3.5-5.11 3.5zm-3-5.5c-.83 0-1.5-.67-1.5-1.5S8.17 6.5 9 6.5s1.5.67 1.5 1.5S9.83 8.5 9 8.5zm6 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
      </svg>
    </div>
    <div class="chat-msg-content">
      <div class="chat-msg-meta">
        <span class="name">Interview Trainer Agent</span>
        <span class="time">Typing...</span>
      </div>
      <div class="chat-msg-bubble typing-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>
  `;
  chatWindow.appendChild(row);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function hideTypingIndicator() {
  const indicator = document.getElementById('chatTypingIndicator');
  if (indicator) indicator.remove();
}

// Toast helper
function showToast(message, type = 'success') {
  const toastEl = document.getElementById('appToast');
  const toastMsg = document.getElementById('toastMessage');
  const icon = toastEl.querySelector('.toast-icon');
  
  toastMsg.textContent = message;
  
  if (type === 'success') {
    toastEl.className = 'toast align-items-center text-white border-0 bg-success glass-toast';
    icon.className = 'fa-solid fa-circle-check toast-icon';
  } else if (type === 'error') {
    toastEl.className = 'toast align-items-center text-white border-0 bg-danger glass-toast';
    icon.className = 'fa-solid fa-circle-xmark toast-icon';
  } else {
    toastEl.className = 'toast align-items-center text-white border-0 bg-info glass-toast';
    icon.className = 'fa-solid fa-circle-info toast-icon';
  }
  
  const toast = new bootstrap.Toast(toastEl);
  toast.show();
}

chatForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  appendMessage(message, 'user');
  chatHistory.push({ role: 'user', content: message });
  saveChatHistory();
  chatInput.value = '';

  // Show dynamic typing indicator
  showTypingIndicator();

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        profile: getProfilePayload(),
        history: chatHistory,
      }),
    });

    const data = await response.json();
    hideTypingIndicator();
    appendMessage(data.reply || 'No response available.', 'assistant');
    chatHistory.push({ role: 'assistant', content: data.reply || 'No response available.' });
    saveChatHistory();
  } catch (err) {
    hideTypingIndicator();
    appendMessage('Sorry, I encountered an error connecting to the Watson Orchestrate API. Please try again.', 'assistant');
    showToast('Failed to get response', 'error');
  }
});

profileForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const response = await fetch('/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(getProfilePayload()),
    });
    const data = await response.json();
    showToast(`Profile saved for ${data.candidate_name}!`);
  } catch (err) {
    showToast('Failed to save profile', 'error');
  }
});

// Drag and drop resume upload zone setup
const fileInput = document.getElementById('resumeFileInput');
const uploadArea = document.getElementById('uploadArea');
const fileNameDisplay = document.getElementById('fileNameDisplay');
const analyzeBtn = document.getElementById('analyzeResumeBtn');

// Click to browse files
uploadArea?.addEventListener('click', () => {
  fileInput.click();
});

// Drag and drop events
uploadArea?.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadArea.parentElement.classList.add('dragover');
});

uploadArea?.addEventListener('dragleave', () => {
  uploadArea.parentElement.classList.remove('dragover');
});

uploadArea?.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadArea.parentElement.classList.remove('dragover');
  if (e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    updateFileDisplay();
  }
});

fileInput?.addEventListener('change', () => {
  updateFileDisplay();
});

function updateFileDisplay() {
  if (fileInput.files.length) {
    const file = fileInput.files[0];
    fileNameDisplay.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    analyzeBtn.disabled = false;
  } else {
    fileNameDisplay.textContent = '';
    analyzeBtn.disabled = true;
  }
}

resumeForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    showToast('Please choose a resume file first.', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('resume', fileInput.files[0]);
  
  // Show uploading status
  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Analyzing...';
  showToast('Analyzing resume...');

  try {
    const response = await fetch('/resume/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    
    // Restore button
    analyzeBtn.disabled = false;
    analyzeBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles me-2"></i>Analyze Resume';
    
    appendMessage(`Resume analyzed. Strengths: ${(data.strengths || []).join(', ') || 'none'}.`, 'assistant');
    chatHistory.push({ role: 'assistant', content: `Resume analyzed. Strengths: ${(data.strengths || []).join(', ') || 'none'}.` });
    saveChatHistory();
    
    showToast('Resume analysis complete!');
  } catch (err) {
    analyzeBtn.disabled = false;
    analyzeBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles me-2"></i>Analyze Resume';
    showToast('Resume analysis failed', 'error');
  }
});

// Copy to clipboard premium feature using event delegation
chatWindow?.addEventListener('click', (event) => {
  const copyBtn = event.target.closest('[title="Copy"]');
  if (!copyBtn) return;
  
  const bubble = copyBtn.closest('.chat-msg-content').querySelector('.chat-msg-bubble');
  if (bubble) {
    navigator.clipboard.writeText(bubble.textContent.trim()).then(() => {
      const icon = copyBtn.querySelector('i');
      icon.className = 'fa-solid fa-check text-success';
      setTimeout(() => {
        icon.className = 'fa-regular fa-copy';
      }, 2000);
    });
  }
});

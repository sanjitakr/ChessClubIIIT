lucide.createIcons();

// Theme Management
class ThemeManager {
  constructor() {
    this.themes = ['light', 'dark', 'auto'];
    this.icons = {
      light: 'sun',
      dark: 'moon',
      auto: 'sun-moon'
    };
    this.theme = localStorage.getItem('chess-club-theme') || 'auto';
    this.init();
  }

  init() {
    this.applyTheme();
    this.setupToggle();
  }

  applyTheme() {
    const html = document.documentElement;

    // if (this.theme === 'auto') {
    //   html.removeAttribute('data-theme');
    // } else {
    //   html.setAttribute('data-theme', this.theme);
    // }
    html.setAttribute('data-theme', this.theme);

    this.updateToggleIcon();
  }

  toggleTheme() {
    const themes = this.themes
    const currentIndex = themes.indexOf(this.theme);
    this.theme = themes[(currentIndex + 1) % themes.length];

    localStorage.setItem('chess-club-theme', this.theme);
    this.applyTheme();
    lucide.createIcons();
  }

  updateToggleIcon() {
    const toggle = document.querySelector('.theme-toggle');
    if (!toggle) return;

    const icons = this.icons

    const iconName = this.icons[this.theme] || this.icons.auto;
    toggle.innerHTML = `<i data-lucide="${iconName}"></i>`;
    toggle.setAttribute('aria-label', `Current theme: ${this.theme}. Click to change.`);
    lucide.createIcons();
  }

  setupToggle() {
    const toggle = document.querySelector('.theme-toggle');
    if (toggle) {
      toggle.addEventListener('click', () => this.toggleTheme());
    }
    lucide.createIcons();
  }
}

// Countdown Timer
class CountdownTimer {
  constructor(element, targetDate) {
    this.element = element;
    this.targetDate = new Date(targetDate);
    this.interval = null;
    this.start();
  }

  start() {
    this.update();
    this.interval = setInterval(() => this.update(), 1000);
  }

  update() {
    const now = new Date();
    const diff = this.targetDate - now;

    if (diff <= 0) {
      this.element.textContent = 'Tournament Started!';
      this.stop();
      return;
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    let display = '';
    if (days > 0) display += `${days}d `;
    if (hours > 0 || days > 0) display += `${hours}h `;
    if (minutes > 0 || hours > 0 || days > 0) display += `${minutes}m `;
    display += `${seconds}s`;

    this.element.textContent = display;
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }
}

// Copy to Clipboard functionality
function copyToClipboard(text, button) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      showCopyFeedback(button, 'Copied!');
    }).catch(() => {
      fallbackCopy(text, button);
    });
  } else {
    fallbackCopy(text, button);
  }
}

function fallbackCopy(text, button) {
  const textArea = document.createElement('textarea');
  textArea.value = text;
  textArea.style.position = 'fixed';
  textArea.style.opacity = '0';
  document.body.appendChild(textArea);

  try {
    textArea.select();
    document.execCommand('copy');
    showCopyFeedback(button, 'Copied!');
  } catch (err) {
    showCopyFeedback(button, 'Failed to copy');
  }

  document.body.removeChild(textArea);
}

function showCopyFeedback(button, message) {
  const originalText = button.textContent;
  button.textContent = message;
  button.disabled = true;

  setTimeout(() => {
    button.textContent = originalText;
    button.disabled = false;
  }, 2000);
}

// Smooth scrolling for anchor links
function setupSmoothScrolling() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));

      if (target) {
        const headerOffset = 80;
        const elementPosition = target.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

        window.scrollTo({
          top: offsetPosition,
          behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
        });
      }
    });
  });
}

function setupMobileNav() {
  const navbars = document.querySelectorAll('.navbar .nav-content');
  navbars.forEach((navContent) => {
    const links = navContent.querySelector('.nav-links');
    const controls = navContent.querySelector('.nav-controls');
    if (!links || navContent.querySelector('.nav-menu-toggle')) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'nav-menu-toggle';
    button.setAttribute('aria-label', 'Toggle navigation');
    button.setAttribute('aria-expanded', 'false');
    button.innerHTML = '<i data-lucide="menu"></i>';

    if (controls) {
      controls.prepend(button);
    } else {
      navContent.appendChild(button);
    }

    button.addEventListener('click', () => {
      const isOpen = links.classList.toggle('open');
      button.setAttribute('aria-expanded', String(isOpen));
      button.innerHTML = `<i data-lucide="${isOpen ? 'x' : 'menu'}"></i>`;
      lucide.createIcons();
    });
  });
}

function setupToastMessages() {
  const messages = Array.from(document.querySelectorAll('[data-toast-message]'));
  if (!messages.length) return;

  let stack = document.querySelector('.toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }

  messages.forEach((message) => {
    const level = message.dataset.toastLevel || 'info';
    const body = message.dataset.toastMessage || message.textContent.trim();
    const toast = document.createElement('div');
    toast.className = `app-toast ${level}`;
    toast.innerHTML = `
      <i data-lucide="${level === 'success' ? 'check-circle-2' : level === 'error' ? 'circle-alert' : level === 'warning' ? 'triangle-alert' : 'info'}"></i>
      <div>
        <div class="toast-title">${level.charAt(0).toUpperCase() + level.slice(1)}</div>
        <div class="toast-body"></div>
      </div>
      <button class="toast-close" type="button" aria-label="Dismiss"><i data-lucide="x"></i></button>
    `;
    toast.querySelector('.toast-body').textContent = body;
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    stack.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 220);
    }, 5200);
  });

  lucide.createIcons();
}

function renderTournaments() {
  const upcomingContainer = document.getElementById('upcoming-tournaments');
  const pastContainer = document.getElementById('past-tournaments');

  if (upcomingContainer) {
    const upcoming = sampleData.tournaments.filter(t => t.type === 'upcoming');
    upcomingContainer.innerHTML = upcoming.map(tournament => `
      <div class="card tournament-card">
        <div class="tournament-header">
          <div>
            <h3 class="tournament-title">${tournament.name}</h3>
            <div class="tournament-date">${new Date(tournament.date).toLocaleDateString('en-IN', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })}</div>
            <p class="text-muted">${tournament.format} / ${tournament.rounds} rounds</p>
          </div>
          <div class="countdown" data-target="${tournament.date}">Loading...</div>
        </div>
        <div class="flex gap-4">
          <a href="#" class="btn btn-primary btn-small">Register</a>
          <a href="#" class="btn btn-secondary btn-small">View Details</a>
        </div>
      </div>
    `).join('');

    // Initialize countdowns
    document.querySelectorAll('.countdown[data-target]').forEach(element => {
      const targetDate = element.getAttribute('data-target');
      new CountdownTimer(element, targetDate);
    });
  }

  if (pastContainer) {
    const past = sampleData.tournaments.filter(t => t.type === 'past');
    pastContainer.innerHTML = past.map(tournament => `
      <div class="card tournament-card">
        <div class="tournament-header">
          <div>
            <h3 class="tournament-title">${tournament.name}</h3>
            <div class="tournament-date">${new Date(tournament.date).toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })}</div>
            <p class="text-muted">${tournament.format} / Winner: <strong>${tournament.winner}</strong></p>
          </div>
        </div>
        <div class="flex gap-4">
          <a href="#" class="btn btn-secondary btn-small">View Results</a>
          <a href="#" class="btn btn-secondary btn-small">Games Archive</a>
        </div>
      </div>
    `).join('');
  }
}

function renderNewsletters() {
  const newsletterGrid = document.querySelector('.newsletter-grid');

  if (newsletterGrid) {
    newsletterGrid.innerHTML = sampleData.newsletters.map(newsletter => `
      <div class="card newsletter-card">
        <div class="newsletter-image">
          <span>Newsletter Image</span>
        </div>
        <div class="newsletter-meta">${new Date(newsletter.date).toLocaleDateString('en-IN')} / ${newsletter.author}</div>
        <h3 class="newsletter-title">${newsletter.title}</h3>
        <p class="newsletter-excerpt">${newsletter.excerpt}</p>
        <a href="newsletter-article.html?slug=${newsletter.slug}" class="btn btn-primary btn-small">Read More</a>
      </div>
    `).join('');
  }
}

// Initialize app
document.addEventListener('DOMContentLoaded', function () {
  lucide.createIcons();
  const resultsContainer = document.getElementById("profile-results");
  const searchInput = document.getElementById("profile-search");
  const ratingFilter = document.getElementById("rating-filter");
  const resultsCount = document.getElementById("results-count");

  // async function loadProfiles() {
  //   const search = searchInput.value.trim();
  //   const rating = ratingFilter.value;

  //   const params = new URLSearchParams({
  //     search,
  //     rating,
  //   });

  //   const response = await fetch(`/api/profiles/?${params.toString()}`);
  //   const data = await response.json();

  //   // Clear and render
  //   resultsContainer.innerHTML = "";
  //   data.profiles.forEach(profile => {
  //     const card = document.createElement("div");
  //     card.classList.add("profile-card");
  //     card.innerHTML = `
  //       <div class="profile-name">
  //         <a href="${profile.profile_url}">${profile.name}</a>
  //       </div>
  //       <div class="profile-rating">Rating: ${profile.rating}</div>
  //       <div class="profile-rank">Rank: ${profile.rank}</div>
  //     `;
  //     resultsContainer.appendChild(card);
  //   });

  //   resultsCount.textContent = `${data.profiles.length} members found`;
  // }
  async function loadProfiles() {
    const container = document.getElementById("profile-results");
    const searchEl = document.getElementById("profile-search");
    const ratingEl = document.getElementById("rating-filter");

    if (!container || !searchEl || !ratingEl) return;

    const search = searchEl.value.trim();
    const rating = ratingEl.value;
    const counter = document.getElementById("results-count");

    if (search === "") {
      container.innerHTML = "";
      if (counter) counter.textContent = "Start typing to search...";
      return;
    }

    const params = new URLSearchParams({ search, rating });
    const response = await fetch(`/api/profiles/?${params.toString()}`);
    const data = await response.json();

    container.innerHTML = "";
    data.profiles.forEach(profile => {
      container.innerHTML += `
        <div class="profile-card">
          <div class="profile-name"><a href="${profile.profile_url}">${profile.name}</a></div>
          <div class="profile-rating">Rating: ${profile.rating}</div>
          <div class="profile-rank">Rank: ${profile.rank}</div>
        </div>`;
    });

    if (counter) counter.textContent = `${data.profiles.length} members found`;
  }

  loadProfiles();

  if (searchInput && ratingFilter) {
    searchInput.addEventListener("input", () => loadProfiles());
    ratingFilter.addEventListener("change", () => loadProfiles());
  }
  // Initialize theme manager
  const themeManager = new ThemeManager();
  setupMobileNav();
  setupToastMessages();
  // Setup smooth scrolling
  setupSmoothScrolling();

  // Render page-specific content
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';

  switch (currentPage) {
    case 'tournaments.html':
      renderTournaments();
      break;
    case 'newsletters.html':
      renderNewsletters();
      break;
  }

  // Global event listeners
  document.addEventListener('click', function (e) {
    // Handle copy buttons
    if (e.target.matches('.copy-btn, .copy-fen')) {
      const text = e.target.getAttribute('data-text') || e.target.getAttribute('data-fen');
      if (text) {
        copyToClipboard(text, e.target);
      }
    }
  });
});

// Future API integration points (commented for reference)
// Future API integration points (commented for reference)
/*
// These functions will be implemented when integrating with external APIs

async function fetchLichessData(username) {
  // Fetch user data from Lichess API
  // const response = await fetch(`https://lichess.org/api/user/${username}`);
  // return response.json();
}

...
*/

class NotificationManager {
  constructor() {
    this.connect();
    this.createToastContainer();
  }

  playAlertSound() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.value = 0.08;
      osc.start();
      osc.stop(ctx.currentTime + 0.15);
    } catch (e) {
      // audio optional
    }
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;
    this.socket = new WebSocket(wsUrl);

    this.socket.onmessage = (e) => {
      const data = JSON.parse(e.data);
      this.handleNotification(data);
    };

    this.socket.onclose = () => {
      setTimeout(() => this.connect(), 5000);
    };
  }

  handleNotification(data) {
    if (data.type === 'new_challenge') {
      this.playAlertSound();
      this.showToast(
        `Challenge from ${data.challenger}!`,
        'Open the lobby to accept or decline',
        () => { window.location.href = '/match/lobby/'; }
      );
      this.updateChallengeBadge(1);
    } else if (data.type === 'challenge_accepted' || data.type === 'challenge_ready') {
      this.playAlertSound();
      const label = data.type === 'challenge_accepted'
        ? `Accepted by ${data.accepter}!`
        : `Match ready vs ${data.opponent}!`;
      this.showToast(label, 'Entering match...', () => {
        window.location.href = data.redirect_url;
      });
      setTimeout(() => { window.location.href = data.redirect_url; }, 800);
    }
  }

  updateChallengeBadge(count) {
    let badge = document.getElementById('challenge-badge');
    if (!badge) {
      const playLink = document.querySelector('a[href="/match/lobby/"]');
      if (!playLink) return;
      badge = document.createElement('span');
      badge.id = 'challenge-badge';
      badge.style.cssText = 'background:#ef4444;color:white;border-radius:50%;padding:2px 6px;font-size:0.65rem;margin-left:4px;font-weight:700;';
      playLink.appendChild(badge);
    }
    badge.textContent = count > 0 ? count : '';
    badge.style.display = count > 0 ? 'inline' : 'none';
  }

  createToastContainer() {
    if (document.getElementById('toast-container')) return;
    const container = document.createElement('div');
    container.id = 'toast-container';
    Object.assign(container.style, {
      position: 'fixed',
      top: '80px',
      right: '20px',
      zIndex: '9999',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px'
    });
    document.body.appendChild(container);

    const style = document.createElement('style');
    style.textContent = `
      .toast-msg {
        background: var(--surface);
        border: 1px solid var(--border);
        border-left: 3px solid var(--accent);
        border-radius: 8px;
        padding: 15px 20px;
        box-shadow: 0 8px 24px var(--shadow-lg);
        color: var(--text);
        cursor: pointer;
        opacity: 0;
        transform: translateX(100%);
        transition: opacity 0.2s ease, transform 0.2s ease;
      }
      .toast-msg.show {
        opacity: 1;
        transform: translateX(0);
      }
      .toast-title { font-weight: bold; color: var(--text); margin-bottom: 5px; }
      .toast-desc { font-size: 0.85rem; color: var(--text-secondary); }
    `;
    document.head.appendChild(style);
  }

  showToast(title, desc, onClick) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast-msg';
    toast.innerHTML = `<div class="toast-title">${title}</div><div class="toast-desc">${desc}</div>`;

    if (onClick) {
      toast.addEventListener('click', onClick);
    }

    container.appendChild(toast);

    // Trigger reflow
    toast.offsetHeight;
    toast.classList.add('show');

    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 5000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // initialize notifications
  new NotificationManager();
});

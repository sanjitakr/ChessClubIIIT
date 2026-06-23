// Tournament Details JavaScript

class TournamentDetails {
  constructor() {
    this.tournamentId = this.getTournamentIdFromURL();
    this.tournament = null;
    this.standings = [];
    this.roundResults = {};
    this.currentRound = 1;
    
    this.init();
  }

  getTournamentIdFromURL() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('id') || 'winter-championship-2025';
  }

  init() {
    this.loadTournamentData();
    this.setupEventListeners();
    this.renderTournament();
  }

  loadTournamentData() {
    // Sample tournament data - in a real app, this would come from an API
    const tournaments = {
      'winter-championship-2025': {
        id: 'winter-championship-2025',
        name: 'IIIT Winter Championship 2025',
        date: '2025-02-15T09:00:00',
        format: 'Classical',
        rounds: 7,
        status: 'upcoming',
        timeControl: '90 minutes + 30 second increment',
        pairingSystem: 'Swiss System',
        entryFee: 'Free for club members',
        prizePool: 'Trophies and certificates',
        registrationDeadline: '2025-02-10T23:59:59',
        venue: 'IIIT Hyderabad Campus',
        maxPlayers: 32,
        currentPlayers: 24
      },
      'rapid-rating-tournament': {
        id: 'rapid-rating-tournament',
        name: 'Rapid Rating Tournament',
        date: '2025-01-25T14:00:00',
        format: 'Rapid',
        rounds: 5,
        status: 'upcoming',
        timeControl: '25 minutes + 10 second increment',
        pairingSystem: 'Swiss System',
        entryFee: 'Free for club members',
        prizePool: 'Rating prizes by category',
        registrationDeadline: '2025-01-22T23:59:59',
        venue: 'IIIT Hyderabad Campus',
        maxPlayers: 24,
        currentPlayers: 18
      }
    };

    this.tournament = tournaments[this.tournamentId] || tournaments['winter-championship-2025'];
    this.generateSampleStandings();
    this.generateSampleSchedule();
  }

  generateSampleStandings() {
    // Sample players for the tournament
    const players = [
      { name: 'Arjun Patel', rating: 2156 },
      { name: 'Priya Sharma', rating: 2134 },
      { name: 'Vikash Kumar', rating: 2089 },
      { name: 'Ananya Singh', rating: 2067 },
      { name: 'Rohit Gupta', rating: 2034 },
      { name: 'Meera Reddy', rating: 2021 },
      { name: 'Karan Joshi', rating: 1987 },
      { name: 'Sneha Iyer', rating: 1976 },
      { name: 'Amit Verma', rating: 1954 },
      { name: 'Divya Nair', rating: 1932 },
      { name: 'Ravi Krishnan', rating: 1898 },
      { name: 'Pooja Agarwal', rating: 1876 },
      { name: 'Suresh Babu', rating: 1854 },
      { name: 'Kavya Menon', rating: 1832 },
      { name: 'Deepak Rao', rating: 1809 },
      { name: 'Nisha Pillai', rating: 1787 },
      { name: 'Manoj Kumar', rating: 1765 },
      { name: 'Sita Devi', rating: 1743 },
      { name: 'Rajesh Sharma', rating: 1721 },
      { name: 'Lakshmi Prasad', rating: 1698 },
      { name: 'Venkat Reddy', rating: 1676 },
      { name: 'Geetha Rani', rating: 1654 },
      { name: 'Sunil Varma', rating: 1632 },
      { name: 'Radha Krishna', rating: 1610 }
    ];

    // Take only the number of current players
    const tournamentPlayers = players.slice(0, this.tournament.currentPlayers);

    this.standings = tournamentPlayers.map((player, index) => ({
      rank: index + 1,
      name: player.name,
      score: 0,
      rating: player.rating,
      buchholz: 0,
      status: 'waiting',
      gamesPlayed: 0
    }));
  }

  generateSampleSchedule() {
    this.schedule = [];
    const startDate = new Date(this.tournament.date);
    
    for (let round = 1; round <= this.tournament.rounds; round++) {
      const roundDate = new Date(startDate);
      roundDate.setHours(startDate.getHours() + (round - 1) * 2); // 2 hours between rounds
      
      this.schedule.push({
        round: round,
        date: roundDate,
        status: round === 1 ? 'upcoming' : 'upcoming'
      });
    }
  }

  setupEventListeners() {
    // Register button
    const registerBtn = document.getElementById('register-btn');
    if (registerBtn) {
      registerBtn.addEventListener('click', () => this.handleRegistration());
    }

    // Share button
    const shareBtn = document.getElementById('share-btn');
    if (shareBtn) {
      shareBtn.addEventListener('click', () => this.handleShare());
    }

    // Refresh standings
    const refreshBtn = document.getElementById('refresh-standings');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => this.refreshStandings());
    }

    // Round filter
    const roundFilter = document.getElementById('round-filter');
    if (roundFilter) {
      roundFilter.addEventListener('change', (e) => this.filterStandings(e.target.value));
    }

    // Round selector
    const roundSelector = document.getElementById('round-selector');
    if (roundSelector) {
      roundSelector.addEventListener('change', (e) => this.showRoundResults(e.target.value));
    }
  }

  renderTournament() {
    this.updatePageTitle();
    this.renderTournamentHeader();
    this.renderTournamentInfo();
    this.renderSchedule();
    this.renderStandings();
    this.renderRoundResults();
  }

  updatePageTitle() {
    document.title = `${this.tournament.name} - IIIT Hyderabad Chess Club`;
    
    const breadcrumb = document.getElementById('tournament-name-breadcrumb');
    if (breadcrumb) {
      breadcrumb.textContent = this.tournament.name;
    }
  }

  renderTournamentHeader() {
    // Tournament status
    const statusBadge = document.querySelector('.tournament-status-badge');
    if (statusBadge) {
      statusBadge.className = `tournament-status-badge ${this.tournament.status}`;
      statusBadge.querySelector('.status-text').textContent = 
        this.tournament.status.charAt(0).toUpperCase() + this.tournament.status.slice(1);
    }

    // Tournament title
    const title = document.getElementById('tournament-title');
    if (title) title.textContent = this.tournament.name;

    // Tournament meta
    const date = document.getElementById('tournament-date');
    if (date) {
      date.textContent = new Date(this.tournament.date).toLocaleDateString('en-IN', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }

    const format = document.getElementById('tournament-format');
    if (format) format.textContent = this.tournament.format;

    const rounds = document.getElementById('tournament-rounds');
    if (rounds) rounds.textContent = this.tournament.rounds;

    const players = document.getElementById('tournament-players');
    if (players) {
      players.textContent = `${this.tournament.currentPlayers}/${this.tournament.maxPlayers}`;
    }
  }

  renderTournamentInfo() {
    const timeControl = document.getElementById('time-control');
    if (timeControl) timeControl.textContent = this.tournament.timeControl;

    const pairingSystem = document.getElementById('pairing-system');
    if (pairingSystem) pairingSystem.textContent = this.tournament.pairingSystem;

    const entryFee = document.getElementById('entry-fee');
    if (entryFee) entryFee.textContent = this.tournament.entryFee;

    const prizePool = document.getElementById('prize-pool');
    if (prizePool) prizePool.textContent = this.tournament.prizePool;

    const deadline = document.getElementById('registration-deadline');
    if (deadline) {
      deadline.textContent = new Date(this.tournament.registrationDeadline).toLocaleDateString('en-IN', {
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }

    const venue = document.getElementById('venue');
    if (venue) venue.textContent = this.tournament.venue;
  }

  renderSchedule() {
    const scheduleContainer = document.getElementById('tournament-schedule');
    if (!scheduleContainer) return;

    if (this.schedule.length === 0) {
      scheduleContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon"><i data-lucide="calendar-x" style="width:32px;height:32px;"></i></div>
          <h4>Schedule Coming Soon</h4>
          <p>Tournament schedule will be published closer to the event date.</p>
        </div>
      `;
      return;
    }

    scheduleContainer.innerHTML = this.schedule.map(item => `
      <div class="schedule-item">
        <div>
          <div class="schedule-round">Round ${item.round}</div>
          <div class="schedule-time">${item.date.toLocaleDateString('en-IN', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          })}</div>
        </div>
        <div class="schedule-status ${item.status}">${item.status}</div>
      </div>
    `).join('');
  }

  renderStandings() {
    const tbody = document.getElementById('standings-tbody');
    if (!tbody) return;

    if (this.standings.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center" style="padding: 2rem;">
            <div class="empty-state">
              <div class="empty-state-icon"><i data-lucide="trophy" style="width:32px;height:32px;"></i></div>
              <h4>No Standings Yet</h4>
              <p>Standings will appear once the tournament begins.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = this.standings.map(player => `
      <tr>
        <td>${player.rank}</td>
        <td class="player-name">${player.name}</td>
        <td class="score">${player.score}</td>
        <td class="rating">${player.rating}</td>
        <td>${player.buchholz}</td>
        <td class="status-${player.status}">${this.getStatusText(player.status)}</td>
      </tr>
    `).join('');
  }

  renderRoundResults() {
    const container = document.getElementById('round-results');
    if (!container) return;

    // For now, show empty state since tournament hasn't started
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon"><i data-lucide="swords" style="width:32px;height:32px;"></i></div>
        <h4>No Results Yet</h4>
        <p>Round results will appear once games are completed.</p>
      </div>
    `;
  }

  getStatusText(status) {
    const statusMap = {
      'waiting': 'Waiting',
      'playing': 'Playing',
      'finished': 'Finished'
    };
    return statusMap[status] || status;
  }

  handleRegistration() {
    if (this.tournament.status === 'completed') {
      alert('This tournament has already finished.');
      return;
    }

    if (this.tournament.currentPlayers >= this.tournament.maxPlayers) {
      alert('This tournament is full. You can join the waiting list.');
      return;
    }

    // In a real app, this would make an API call
    alert(`Registration for ${this.tournament.name} would be processed here. Please contact chess@iiit.ac.in to register.`);
  }

  handleShare() {
    const url = window.location.href;
    const text = `Check out ${this.tournament.name} at IIIT Hyderabad Chess Club!`;
    
    if (navigator.share) {
      navigator.share({
        title: this.tournament.name,
        text: text,
        url: url
      });
    } else {
      // Fallback: copy to clipboard
      navigator.clipboard.writeText(`${text} ${url}`).then(() => {
        alert('Tournament link copied to clipboard!');
      }).catch(() => {
        alert(`Share this tournament: ${url}`);
      });
    }
  }

  refreshStandings() {
    // In a real app, this would fetch fresh data from the server
    const refreshBtn = document.getElementById('refresh-standings');
    const originalText = refreshBtn.textContent;
    
    refreshBtn.textContent = 'Refreshing...';
    refreshBtn.disabled = true;
    
    setTimeout(() => {
      refreshBtn.textContent = originalText;
      refreshBtn.disabled = false;
      // For now, just re-render the same data
      this.renderStandings();
    }, 1000);
  }

  filterStandings(filter) {
    // In a real app, this would filter the standings based on the selected option
    console.log('Filtering standings by:', filter);
    this.renderStandings();
  }

  showRoundResults(round) {
    // In a real app, this would show results for the selected round
    console.log('Showing results for round:', round);
    this.renderRoundResults();
  }
}

// Initialize tournament details when page loads
document.addEventListener('DOMContentLoaded', function() {
  new TournamentDetails();
});
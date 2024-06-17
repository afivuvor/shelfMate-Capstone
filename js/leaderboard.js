document.addEventListener('DOMContentLoaded', () => {
  // Fetch leaderboard data and display it
  async function fetchAndDisplayLeaderboard() {
    const baseURL = 'http://34.249.29.18:8080'; // Adjust to match your Flask app's URL
    const token = localStorage.getItem('jwt'); // Assuming the token is stored in localStorage

    try {
      const response = await fetch(`${baseURL}/leaderboard`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch leaderboard data');
      }

      const leaderboardData = await response.json();

      const leaderboardBody = document.getElementById('leaderboardBody');
      leaderboardBody.innerHTML = ''; // Clear existing rows

      leaderboardData.forEach((user, index) => {
        const row = document.createElement('tr');

        let rankContent = index + 1;
        let rankCellHTML = `${rankContent}`;
        if (rankContent === 1) {
          rankCellHTML = `<img src="img/awards/trophy-gold.png" alt="Gold Trophy" class="rank-icon"> ${rankContent}`;
          row.style.borderBottom = '1.5px solid rgb(245, 107, 144)';
        } else if (rankContent === 2) {
          rankCellHTML = `<img src="img/awards/trophy-silver.png" alt="Silver Trophy" class="rank-icon"> ${rankContent}`;
        }

        let badgesListHTML = "None"; // Default if no badges
        if (user.badges.length > 0) {
          badgesListHTML = user.badges.map(badge => `<img src="img/awards/badge-${badge.toLowerCase()}.png" alt="${badge} badge" class="badge-icon">`).join(" ");
        }

        row.innerHTML = `
          <td>${rankCellHTML}</td>
          <td>${user.username}</td>
          <td>${user.points}</td>
          <td>${badgesListHTML}</td>
        `;
        leaderboardBody.appendChild(row);
      });
    } catch (error) {
      console.error('Error:', error);
    }
  }

  fetchAndDisplayLeaderboard();
});

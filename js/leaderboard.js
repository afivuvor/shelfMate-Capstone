document.addEventListener('DOMContentLoaded', () => {
  // Fetch leaderboard data and display it
  async function fetchAndDisplayLeaderboard() {
    const baseURL = 'http://127.0.0.1:8080'; // Adjust to match your Flask app's URL
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
        let badgesList = "None"; // Default if no badges

        if (user.badges.length > 0) {
          badgesList = user.badges.join(", ");
        }

        row.innerHTML = `
          <td>${index + 1}</td>
          <td>${user.username}</td>
          <td>${user.points}</td>
          <td>${badgesList}</td>
        `;
        leaderboardBody.appendChild(row);
      });
    } catch (error) {
      console.error('Error:', error);
    }
  }

  fetchAndDisplayLeaderboard();
});

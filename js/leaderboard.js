document.addEventListener('DOMContentLoaded', () => {
    // Fetch leaderboard data and display it
    function fetchAndDisplayLeaderboard() {
      const baseURL = 'http://127.0.0.1:8080'; // Adjust to match your Flask app's URL
      fetch(`${baseURL}/leaderboard`)
        .then(response => response.json())
        .then(data => {
          const leaderboardBody = document.getElementById('leaderboardBody');
          leaderboardBody.innerHTML = ''; // Clear any existing content

          data.forEach((user, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
              <td>${index + 1}</td>
              <td>${user.username}</td>
              <td>${user.booksRead}</td>
              <td>${user.points}</td>
            `;
            leaderboardBody.appendChild(row);
          });
        })
        .catch(error => {
          console.error('Error fetching leaderboard data:', error);
        });
      }
  });
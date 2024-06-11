document.addEventListener('DOMContentLoaded', () => {
  // Fetch leaderboard data and display it
  async function fetchAndDisplayLeaderboard() {
    const baseURL = 'http://127.0.0.1:8080'; // Adjust to match your Flask app's URL
    const token = localStorage.getItem('jwt'); // Assuming the token is stored in localStorage

    try {
      // const response = await fetch(`${baseURL}/leaderboard`, {
      //   method: 'GET',
      //   headers: {
      //     'Authorization': `Bearer ${token}`
      //   }
      // });

      fetch('http://127.0.0.1:8080/leaderboard', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      const data = await response.json();
      const leaderboardBody = document.getElementById('leaderboardBody');
      leaderboardBody.innerHTML = ''; // Clear any existing content

      data.forEach((user, index) => {
        // Render the badges as a comma-separated list
        const badgesList = Array.isArray(user.badges) ? user.badges.join(", ") : "N/A";
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${index + 1}</td>
          <td>${user.username}</td>
          <td>${user.points}</td>
          <td>${badgesList}</td>
        `;
        leaderboardBody.appendChild(row);
      });
    } catch (error) {
      console.error('Error fetching leaderboard data:', error);
    }
  }
  
  document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");
    fetchAndDisplayLeaderboard();  // Calling the fetch function here to make sure it's being executed.
  });
});
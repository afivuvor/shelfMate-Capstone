document.addEventListener('DOMContentLoaded', () => {
    const signOutLink = document.getElementById('signOutLink');

    signOutLink.addEventListener('click', (event) => {
        event.preventDefault(); // Prevent the default link behavior

        // Clear the JWT token from localStorage
        localStorage.removeItem('jwt');

        // Redirect to the sign-in page
        window.location.href = 'users/signIn.html';
    });

    const token = localStorage.getItem('jwt');

    if (!token) {
        console.error('User not authenticated');
        return;
    }

    fetch('http://127.0.0.1:8080/getUserProfile', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Failed to fetch user profile');
        }
        return response.json();
    })
    .then(data => {
        console.log(data); // Log data received from the backend for debugging
        if (data.error) {
            console.error(data.error);
            return;
        }

        document.getElementById('username').textContent = data.username;
        document.getElementById('email').textContent = data.email;
        document.getElementById('gender').textContent = data.gender;
        document.getElementById('booksRead').textContent = data.booksRead;
        document.getElementById('pointsEarned').textContent = data.points;
        
        // Display badges as a comma-separated list of badge names
        const badgesList = Array.isArray(data.badges) && data.badges.length > 0 ? data.badges.join(", ") : "None";
        document.getElementById('badgesEarned').textContent = badgesList;

        document.getElementById('streaks').textContent = `${data.streak} days`;
    })
    .catch(error => {
        console.error('Error fetching user profile:', error);
    });
});

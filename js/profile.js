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
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error(data.error);
            return;
        }

        document.getElementById('username').textContent = data.username;
        document.getElementById('email').textContent = data.email;
        document.getElementById('gender').textContent = data.gender || 'Not specified';
        document.getElementById('booksRead').textContent = data.booksRead;
        document.getElementById('pointsEarned').textContent = data.points;
        document.getElementById('badgesEarned').textContent = data.badges;
        document.getElementById('streaks').textContent = `${data.streak} days`;
    })
    .catch(error => {
        console.error('Error fetching user profile:', error);
    });
});

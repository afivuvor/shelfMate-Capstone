document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('fileInput');
    const submitButton = document.getElementById('submitButton');
    const reader = document.getElementById('reader');
    let currentPage = 0;
    let startTime = 0;
    let timeSpent = 0;
    let pagesRead = new Set();
    let book = null;
    let token = localStorage.getItem('jwt');

    if (!token) {
        console.error('User not authenticated');
        return;
    }

    submitButton.addEventListener('click', function() {
        const file = fileInput.files[0];
        if (file) {
            if (file.type === 'application/pdf') {
                renderPDF(file);
            } else if (file.type === 'application/epub+zip') {
                renderEPUB(file);
            } else {
                alert('Unsupported file type');
            }
        } else {
            alert('No file selected');
        }
    });

    function renderPDF(file) {
        const fileURL = URL.createObjectURL(file);
        reader.innerHTML = ''; // Clear previous content

        const loadingTask = pdfjsLib.getDocument(fileURL);
        loadingTask.promise.then(pdf => {
            for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                pdf.getPage(pageNum).then(page => {
                    const scale = 1.5;
                    const viewport = page.getViewport({ scale: scale });

                    const canvas = document.createElement('canvas');
                    const context = canvas.getContext('2d');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;

                    const renderContext = {
                        canvasContext: context,
                        viewport: viewport
                    };
                    const renderTask = page.render(renderContext);
                    renderTask.promise.then(() => {
                        console.log(`Page ${pageNum} rendered`);
                    });

                    reader.appendChild(canvas);
                });
            }

            startTracking();
        });
    }
    
    function startTracking() {
        startTime = Date.now();
        window.addEventListener('scroll', trackScroll);
    }

    function trackScroll() {
        const pageHeight = window.innerHeight;
        const scrollPosition = window.scrollY;
        const totalPages = document.getElementById('reader').children.length;
        const scrolledPages = Math.ceil(scrollPosition / pageHeight);
        timeSpentOnPage = Date.now() - startTime;
    
        // Update current page number
        currentPage = scrolledPages;
        console.log('Current page:', currentPage);
    
        // Track pages read
        pagesRead.add(currentPage);
    
        // Check and award badges
        checkAndAwardBadges();
    
        // If user reaches the last page, remove scroll event listener and update leaderboard
        if (scrolledPages === totalPages) {
            window.removeEventListener('scroll', trackScroll);
            console.log('Pages read:', pagesRead);
            updateLeaderboard();
        }
    }

    // Function to calculate points
    function calculatePoints(timeSpent, pagesRead) {
        console.log('Time spent:', timeSpent);
        return Math.floor(timeSpent / 60000) + pagesRead;
    }

    // Function to update points on the server
    function updatePoints(points) {
        fetch('http://127.0.0.1:8080/updatePoints', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ points })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Points updated:', data);
        })
        .catch(error => {
            console.error('Error updating points:', error);
        });
    }

    // Update badges on the server
    function updateBadges(badges) {
        fetch('http://127.0.0.1:8080/updateBadges', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ badges })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Badges updated:', data);
        })
        .catch(error => {
            console.error('Error updating badges:', error);
        });
    }

    // Function to check and award badges
    function checkAndAwardBadges() {
        // Logic to check if user earns badges
        let earnedBadges = [];

        // Example logic: check if user reads 5 pages consecutively [FIX THIS LOGIC!!!]
        if (pagesRead.size >= 5) {
            earnedBadges.push('Consecutive Reader');
        }

        // Update badges if user earned any
        if (earnedBadges.length > 0) {
            updateBadges(earnedBadges);
        }
    }

    // Update leaderboard position on the server
    function updateLeaderboardPosition(leaderboardScore) {
        fetch('http://127.0.0.1:8080/updateLeaderboardPosition', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ leaderboardScore })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Leaderboard position updated:', data);
        })
        .catch(error => {
            console.error('Error updating leaderboard position:', error);
        });
    }

    // Function to calculate leaderboard score
    function calculateLeaderboardScore(points, badges) {
        // Logic to calculate leaderboard score based on points and badges
        let leaderboardScore = points + badges.length;
        return leaderboardScore;
    }

    // Function to update leaderboard score
    function updateLeaderboard() {
        // Fetch user's points and badges
        const points = calculatePoints(timeSpent, pagesRead.size);
        const badges = Array.from(pagesRead); // For demonstration, you can replace this with actual badge data
        
        // Calculate leaderboard score
        const leaderboardScore = calculateLeaderboardScore(points, badges);

        // Update leaderboard position on the server
        updateLeaderboardPosition(leaderboardScore);
    }

    // Inside the beforeunload event listener
    window.addEventListener('beforeunload', () => {
        const timeSpent = Date.now() - startTime;
        const pagesReadCount = pagesRead.size;
    
        // Only calculate and update points if the user has actually read something
        if (pagesReadCount > 0) {
            const points = calculatePoints(timeSpent, pagesReadCount);
            updatePoints(points);
        }
    });    
});



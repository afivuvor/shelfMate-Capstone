document.addEventListener("DOMContentLoaded", async () => {
    const BASE_URL = "http://127.0.0.1:8080"; // Adjust as per your backend URL
    const token = localStorage.getItem("jwt");

    if (!token) {
        console.error("User not authenticated!");
        window.alert("Please log in to use this app!");
        return;
    }

    let username = null;
    let book = null;
    let rendition = null;
    let pagesRead = 0;
    let startTime = null;

    try {
        // Fetch user profile to get username
        const userProfileResponse = await fetch(`${BASE_URL}/getUserProfile`, {
            method: "GET",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
            },
        });

        if (!userProfileResponse.ok) {
            console.log("Failed to fetch user profile");
            return;
        }

        const userData = await userProfileResponse.json();
        username = userData.username;

        // Function to fetch EPUB from server
        async function fetchEPUBFromServer(username) {
            const userFilesResponse = await fetch(`${BASE_URL}/userFiles?username=${username}`, {
                method: "GET",
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (!userFilesResponse.ok) {
                console.log("Failed to fetch user files");
                return null;
            }

            const userFiles = await userFilesResponse.json();
            let epubUrl = null;
            let latestFile = null;

            // Find latest EPUB file
            for (const file of userFiles) {
                if (file.name.toLowerCase().endsWith(".epub")) {
                    if (!latestFile || new Date(file.lastModified) > new Date(latestFile.lastModified)) {
                        latestFile = file;
                    }
                }
            }

            if (!latestFile) {
                throw new Error("No EPUB file found for the user");
            }

            return latestFile.url; // Return URL of latest EPUB file
        }

        // EPUB.js integration - function to load EPUB
        function loadEPUB(url) {
            // Clean up existing book and rendition
            if (book) {
                rendition.destroy();
                book.destroy();
                book = null;
                rendition = null;
            }

            // Initialize new book and rendition
            book = ePub(url);
            rendition = book.renderTo("epubViewer", {
                width: "100%",
                height: 600,
                ignoreClass: "annotator-hl",
                manager: "continuous",
            });

            // Display initial page
            rendition.display(6);

            // Navigation buttons
            var next = document.getElementById("next");
            var prev = document.getElementById("prev");

            next.addEventListener("click", function () {
                rendition.next();
            });

            prev.addEventListener("click", function () {
                rendition.prev();
            });

            // Handle key events
            document.addEventListener("keyup", function (e) {
                switch (e.keyCode) {
                    case 37: // Left arrow key
                        rendition.prev();
                        break;
                    case 39: // Right arrow key
                        rendition.next();
                        break;
                }
            });

            // Error handling
            book.opened.catch(function (error) {
                console.error("Error opening book", error);
            });

            // Fetch metadata including total page count
            book.ready.then(() => {
                // Fetch total page count
                const pageCount = book.locations.total;
                // Update DOM with total page count
                document.getElementById("page_count").textContent = pageCount;
            });

            // Track page changes
            rendition.on("relocated", (location) => {
                const page = location.start.displayed.page;
                console.log(`Page ${page} displayed`);
                // Update page number
                document.getElementById("page_num").textContent = page;
                // Track pages read
                trackPageRead();
            });
        }

        // Handle file upload
        document.getElementById("fileInput").addEventListener("change", handleFileSelect);

        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) {
                alert("No file selected");
                return;
            }

            const formData = new FormData();
            formData.append("file", file);
            formData.append("username", username);

            try {
                const uploadResponse = await fetch(`${BASE_URL}/upload`, {
                    method: "POST",
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                    body: formData,
                });

                if (!uploadResponse.ok) {
                    console.log("Failed to upload file");
                    return;
                }

                const uploadResult = await uploadResponse.json();
                console.log(uploadResult.message);

                // Determine file type based on MIME type or file extension
                const fileType = file.type; // MIME type
                const fileName = file.name; // File name

                // Redirect based on file type
                if (fileType === "application/pdf" || fileName.toLowerCase().endsWith(".pdf")) {
                    window.location.href = "read.html"; // Redirect to read-pdf.html for PDF
                } else if (fileName.toLowerCase().endsWith(".epub")) {
                    const epubUrl = await fetchEPUBFromServer(username);
                    if (epubUrl) {
                      loadEPUB(epubUrl); // Redirect to read.html for EPUB
                    } else {
                      console.error("Failed to fetch EPUB URL");
                    }
                } else {
                    console.error("Unsupported file type");
                    // alert("Hi friend! File type should be pdf or epub :)")
                }

            } catch (error) {
                console.error("Error handling file select:", error);
            }
        }

        // Track pages read and time spent per page
        function trackPageRead() {
            if (!startTime) {
                startTime = new Date();
            } else {
                const endTime = new Date();
                const timeSpentSeconds = (endTime - startTime) / 1000;
                startTime = endTime; // Reset start time for next page
                if (timeSpentSeconds >= 60) {
                    pagesRead++;
                    console.log(`Total pages read: ${pagesRead}`);
                }
                // Update streak, points, badges, leaderboard as needed
                updateStreakAndPoints();
            }
        }

        // Update streak and points on daily sign-in or page navigation
        async function updateStreakAndPoints() {
            const response = await fetch(`${BASE_URL}/updateStreakAndPoints`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    pages_read: pagesRead,
                    daily_sign_in: true // Modify as per your actual logic
                })
            });

            if (response.ok) {
                const result = await response.json();
                console.log(result.message);
                console.log('Points after update:', result.points);
                await checkAndAwardBadges(result.points);
            } else {
                const error = await response.json();
                console.error('Error updating streak and points:', error);
            }
        }

        // Award badges based on points
        async function checkAndAwardBadges(points) {
            // Example logic to award badges based on points
            const badgeCriteria = [
                { threshold: 10000, badge: 'shelfMate' },
                { threshold: 5000, badge: 'Gold' },
                { threshold: 2000, badge: 'Silver' },
                { threshold: 1000, badge: 'Bronze' },
            ];

            for (const { threshold, badge } of badgeCriteria) {
                if (points >= threshold) {
                    console.log(`Awarding badge for points: ${points}`);
                    await updateBadge(badge);
                }
            }
        }

        // Update user's badge status
        async function updateBadge(badge) {
            // Example logic to update badges
            const response = await fetch(`${BASE_URL}/updateBadges`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ badge })
            });

            if (response.ok) {
                const result = await response.json();
                console.log(result.message);
            } else {
                const error = await response.json();
                console.error('Error updating badge:', error);
            }
        }

        function getParameterByName(name) {
          const url = window.location.href;
          name = name.replace(/[\[\]]/g, '\\$&');
          const regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)');
          const results = regex.exec(url);
          if (!results) return null;
          if (!results[2]) return '';
          return decodeURIComponent(results[2].replace(/\+/g, ' '));
        }

        // Fetch and render PDF from URL parameter
        try {
          const url = getParameterByName('url');
          console.log('URL:', url);
          if (url) {
            loadEPUB(url);
          } else {
            // Initial load of EPUB
            const epubUrl = await fetchEPUBFromServer(username);
            if (epubUrl) {
              loadEPUB(epubUrl);
            }
          }
        } catch (error) {
          console.error('Error fetching epub from URL parameter:', error);
        }

    } catch (error) {
        console.error("Error initializing EPUB viewer:", error);
        console.log("Failed to initialize EPUB viewer. Please refresh the page.");
    }
});

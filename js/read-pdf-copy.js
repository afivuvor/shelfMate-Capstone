document.addEventListener('DOMContentLoaded', async () => {
    const BASE_URL = 'https://shelfmate-app.online';
    const token = localStorage.getItem('jwt');

    if (!token) {
        console.error('User not authenticated');
        window.alert('Please login to use the app!');
        return;
    }

    let username = null;

    try {
        const userProfileResponse = await fetch(`${BASE_URL}/getUserProfile`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });

        if (!userProfileResponse.ok) {
            console.log('Failed to fetch user profile');
            return;
        }

        const userData = await userProfileResponse.json();
        username = userData.username;

        const pdfjsLib = window['pdfjs-dist/build/pdf'];
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

        let pdfDoc = null,
            pageNum = 1,
            pageRendering = false,
            pageNumPending = null,
            canvas = document.getElementById('pdfViewer'),
            ctx = canvas ? canvas.getContext('2d') : null,
            startTime = null,
            pagesRead = 0;

        function getUrlParameter(name) {
            name = name.replace(/[\[]/, '\\[').replace(/[\]]/, '\\]');
            const regex = new RegExp('[\\?&]' + name + '=([^&#]*)');
            const results = regex.exec(location.search);
            return results === null ? '' : decodeURIComponent(results[1].replace(/\+/g, ' '));
        }

        const pdfUrl = getUrlParameter('url');
        // console.log('PDF URL:', pdfUrl);

        async function fetchPdf(url) {
            return pdfjsLib.getDocument(url).promise;
        }

        function showCanvas() {
            canvas.style.display = 'block';
        }

        function renderPage(num) {
            if (!pdfDoc || !canvas || !ctx) return;
            pageRendering = true;
        
            pdfDoc.getPage(num).then(page => {
                const viewport = page.getViewport({ scale: 1 });
                const reader = document.getElementById('reader');
                if (!reader) return;
        
                const readerWidth = reader.clientWidth;
                const readerHeight = reader.clientHeight;
        
                // Calculate scale based on the reader dimensions
                const scale = Math.min(readerWidth / viewport.width, readerHeight / viewport.height);
                
                // Include the device pixel ratio
                const devicePixelRatio = window.devicePixelRatio || 1;
                const scaledViewport = page.getViewport({ scale: scale * devicePixelRatio });
        
                // Set the canvas dimensions, taking into account the device pixel ratio
                canvas.height = scaledViewport.height;
                canvas.width = scaledViewport.width;
        
                // Ensure the canvas is displayed correctly
                canvas.style.width = `${scaledViewport.width / devicePixelRatio}px`;
                canvas.style.height = `${scaledViewport.height / devicePixelRatio}px`;
        
                const renderContext = {
                    canvasContext: ctx,
                    viewport: scaledViewport
                };
        
                const renderTask = page.render(renderContext);
        
                renderTask.promise.then(() => {
                    pageRendering = false;
                    if (pageNumPending !== null) {
                        renderPage(pageNumPending);
                        pageNumPending = null;
                    }
                    startTime = new Date();
                    showCanvas();
        
                    // Hide image and paragraph after successful render
                    const img = reader.querySelector('img');
                    const p = reader.querySelector('p');
                    if (img) img.style.display = 'none';
                    if (p) p.style.display = 'none';
                });
            });
        
            const pageNumElement = document.getElementById('page_num');
            if (pageNumElement) pageNumElement.textContent = `Page ${num}`;
        }        

        function queueRenderPage(num) {
            if (pageRendering) {
                pageNumPending = num;
            } else {
                renderPage(num);
            }
        }

        function onPrevPage() {
            if (pageNum <= 1) {
                return;
            }
            trackPageTime();
            pageNum--;
            queueRenderPage(pageNum);
        }

        function onNextPage() {
            if (pageNum >= pdfDoc.numPages) {
                return;
            }
            trackPageTime();
            pageNum++;
            queueRenderPage(pageNum);
            updateStreakAndPoints();
        }

        function trackPageTime() {
            if (!startTime) return;
            const endTime = new Date();
            const timeSpent = (endTime - startTime) / 1000;
            if (timeSpent >= 45) {
                pagesRead++;
            }
            startTime = null;
        }

        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) {
                alert('No file selected');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('username', username);

            try {
                const uploadResponse = await fetch(`${BASE_URL}/upload`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData
                });

                if (!uploadResponse.ok) {
                    alert('Failed to upload file');
                    return;
                }

                const uploadResult = await uploadResponse.json();
                // console.log(uploadResult.message);

                // Clear previous PDF state
                pdfDoc = null;
                pageNum = 1;
                pageRendering = false;
                pageNumPending = null;

                // Determine file type based on MIME type or file extension
                const fileType = file.type; // MIME type
                const fileName = file.name; // File name

                // Specify read page based on type of file uploaded
                if (fileType === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf')) {
                    // Fetch and render the uploaded PDF
                    pdfDoc = await fetchPdf(URL.createObjectURL(file));
                    const pageCountElement = document.getElementById('page_count');
                    if (pageCountElement) pageCountElement.textContent = `Total Pages: ${pdfDoc.numPages}`;
                    renderPage(pageNum);

                    // Show image and paragraph if hidden
                    const reader = document.getElementById('reader');
                    if (reader) {
                        reader.querySelector('img').style.display = 'block';
                        reader.querySelector('p').style.display = 'block';
                    }
                } else if (fileName.toLowerCase().endsWith('.epub')) {
                    window.location.href = 'read-epub.html'; // Redirect to read.html for EPUB
                } else {
                    console.error('Unsupported file type');
                }
            } catch (error) {
                console.error('Error handling file select:', error);
            }
        }

        async function updateStreakAndPoints() {
            const response = await fetch(`${BASE_URL}/updateStreakAndPoints`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    pages_read: pagesRead,
                    daily_sign_in: true
                })
            });

            if (response.ok) {
                const result = await response.json();
                // console.log(result.message);
                // console.log('Points after update:', result.points);
                await checkAndAwardBadges(result.points);
            } else {
                const error = await response.json();
                console.error('Error updating streak and points:', error);
            }
        }

        async function checkAndAwardBadges(points) {
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

        async function updateBadge(badge) {
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
                // console.log(result.message);
            } else {
                const error = await response.json();
                console.error('Error updating badge:', error);
            }
        }

        document.getElementById('fileInput').addEventListener('change', handleFileSelect);
        window.addEventListener('beforeunload', updateStreakAndPoints);

        document.addEventListener('keydown', event => {
            switch (event.key) {
                case 'ArrowLeft':
                    onPrevPage();
                    break;
                case 'ArrowRight':
                    onNextPage();
                    break;
            }
        });


        // Attach click event listeners to the arrows
        document.getElementById('prev').addEventListener('click', function(event) {
            event.preventDefault(); // Prevent the default anchor behavior
            onPrevPage();
        });

        document.getElementById('next').addEventListener('click', function(event) {
            event.preventDefault(); // Prevent the default anchor behavior
            onNextPage();
        });

        // Initially fetch the PDF from the server (if any)
        try {
            if (pdfUrl) {
                // Load PDF based on URL parameter
                pdfDoc = await fetchPdf(pdfUrl);
                const pageCountElement = document.getElementById('page_count');
                if (pageCountElement) pageCountElement.textContent = `Total Pages: ${pdfDoc.numPages}`;
                renderPage(pageNum);

                // Show image and paragraph if hidden
                const reader = document.getElementById('reader');
                if (reader) {
                    reader.querySelector('img').style.display = 'block';
                    reader.querySelector('p').style.display = 'block';
                }
            } else {
                console.log('No PDF URL provided');
            }
        } catch (error) {
            console.error('Error fetching PDF:', error);
        }

    } catch (error) {
        console.error('Error initializing PDF viewer:', error);
        alert('Failed to initialize PDF viewer. Please refresh the page.');
    }
});
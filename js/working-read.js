document.addEventListener('DOMContentLoaded', () => {
    let token = localStorage.getItem('jwt');
    if (!token) {
        console.error('User not authenticated');
        return;
    }

    const BASE_URL = 'http://34.249.29.18:8080';
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

    function renderPage(num) {
        if (!pdfDoc || !canvas || !ctx) return;
        pageRendering = true;
        pdfDoc.getPage(num).then(page => {
            const viewport = page.getViewport({ scale: 1 });
            const reader = document.getElementById('reader');
            if (!reader) return;
            const readerWidth = reader.clientWidth;
            const readerHeight = reader.clientHeight;

            // Calculate scale to fit the page within the reader
            const scale = Math.min(readerWidth / viewport.width, readerHeight / viewport.height);

            const scaledViewport = page.getViewport({ scale });
            canvas.height = scaledViewport.height;
            canvas.width = scaledViewport.width;

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
        const timeSpent = (endTime - startTime) / 1000; // time in seconds
        if (timeSpent >= 60) {
            pagesRead++;
        }
        startTime = null;
    }

    async function handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            const fileReader = new FileReader();
            fileReader.onload = function() {
                const typedArray = new Uint8Array(this.result);
                pdfjsLib.getDocument(typedArray).promise.then(pdfDoc_ => {
                    pdfDoc = pdfDoc_;
                    const pageCountElement = document.getElementById('page_count');
                    if (pageCountElement) pageCountElement.textContent = `Total Pages: ${pdfDoc.numPages}`;
                    pageNum = 1;

                    const submitButton = document.getElementById('submitButton');
                    if (submitButton) {
                        submitButton.addEventListener('click', async () => {
                            queueRenderPage(pageNum);
                            const reader = document.getElementById('reader');
                            if (reader) {
                                const img = reader.querySelector('img');
                                const p = reader.querySelector('p');
                                if (img) img.style.display = 'none';
                                if (p) p.style.display = 'none';
                            }

                            const formData = new FormData();
                            formData.append('file', file);
                            formData.append('username', username); // Ensure username is defined

                            try {
                                const response = await fetch(`${BASE_URL}/upload`, {
                                    method: 'POST',
                                    headers: {
                                        'Authorization': `Bearer ${token}`
                                    },
                                    body: formData
                                });

                                if (!response.ok) {
                                    throw new Error('File upload failed');
                                }

                                const result = await response.json();
                                alert(result.message);
                                fetchAndDisplayFiles(); // Refresh the list of files
                            } catch (error) {
                                console.error('Error uploading file:', error);
                            }
                        });
                    }
                });
            };
            fileReader.readAsArrayBuffer(file);
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
            console.log(result.message);
            console.log('Points after update:', result.points); // Log the updated points
            await checkAndAwardBadges(result.points); // After the points are updated
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
            console.log(result.message);
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
});

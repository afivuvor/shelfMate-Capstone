document.addEventListener('DOMContentLoaded', () => {
    const BASE_URL = 'https://shelfmate-app.online';
    let url = ''

    function getUsernameFromToken(token) {
        try {
            const decoded = jwt_decode(token);
            return decoded.username;
        } catch (error) {
            console.error('Error decoding token:', error);
            return null;
        }
    }

    let token = localStorage.getItem('jwt');
    if (!token) {
        console.error('User not authenticated');
        return;
    }

    let username = getUsernameFromToken(token);
    if (!username) {
        console.error('Username not found in token');
        return;
    }

    async function fetchAndDisplayFiles() {
        try {
            const response = await fetch(`${BASE_URL}/userFiles`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                throw new Error('Failed to fetch user files');
            }

            const files = await response.json();
            const booksContainer = document.getElementById('booksContainer');
            booksContainer.innerHTML = '';

            files.forEach(file => {
                url = file.url;
                console.log('File:', url);
                if (file.name.toLowerCase().endsWith('.pdf')) {
                    renderPdfCover(file.url, file.name);
                } else if (file.name.toLowerCase().endsWith('.epub')) {
                    renderEpubCover(url, file.name);
                }
            });
        } catch (error) {
            console.error('Error fetching files:', error);
        }
    }

    async function renderPdfCover(url, name) {
        const pdfjsLib = window['pdfjs-dist/build/pdf'];
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

        try {
            const pdf = await pdfjsLib.getDocument(url).promise;
            const page = await pdf.getPage(1);
            const viewport = page.getViewport({ scale: 1 });
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            canvas.height = viewport.height;
            canvas.width = viewport.width;
            await page.render({ canvasContext: context, viewport: viewport }).promise;
            const img = document.createElement('img');
            img.src = canvas.toDataURL();
            img.alt = name;
            img.className = 'book-cover';
            img.onclick = () => window.location.href = `read.html?url=${url}`;
            console.log('url:', url);
            document.getElementById('booksContainer').appendChild(img);
        } catch (error) {
            console.error('Error rendering PDF cover:', error);
        }
    }

    async function renderEpubCover(url, name) {
        try {
            const formData = new FormData();
            const response = await fetch(url);
            const blob = await response.blob();
            formData.append('file', blob, name);

            const coverResponse = await fetch(`${BASE_URL}/epub_cover`, {
                method: 'POST',
                body: formData
            });

            if (!coverResponse.ok) {
                throw new Error('Failed to fetch EPUB cover');
            }

            const coverBlob = await coverResponse.blob();
            const coverUrl = URL.createObjectURL(coverBlob);

            const img = document.createElement('img');
            img.src = coverUrl;
            img.alt = name;
            img.className = 'book-cover';
            img.onclick = () => window.location.href = `read-epub.html?url=${url}`;
            document.getElementById('booksContainer').appendChild(img);
        } catch (error) {
            console.error('Error rendering EPUB cover:', error);
        }
    }

    fetchAndDisplayFiles();
});

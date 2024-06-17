document.addEventListener('DOMContentLoaded', () => {
  // Function to perform search and store results in session storage
  function searchBooks() {
      const query = document.getElementById("searchInput").value.trim();
      if (!query) {
          console.log("Empty search query. Please enter a search term.");
          return;
      }

      const baseURL = 'http://34.249.29.18:8080';
      fetch(`${baseURL}/search?q=${encodeURIComponent(query)}`)
          .then(response => response.json())
          .then(data => {
              // Store search results in session storage
              sessionStorage.setItem('searchResults', JSON.stringify(data));
              // Redirect to home/index page
              window.location.href = 'index.html';
          })
          .catch(error => {
              console.error('Error searching books:', error);
          });
  }

  // Add event listener for keydown event on the search input field
  const searchInput = document.getElementById("searchInput");
  if (searchInput) {
      searchInput.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
              searchBooks();
          }
      });
  } else {
      console.error('Search input element not found in the current page');
  }
});





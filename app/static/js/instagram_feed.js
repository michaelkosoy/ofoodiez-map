document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('ig-posts-grid');
    const loading = document.getElementById('ig-posts-loading');
    const emptyState = document.getElementById('ig-posts-empty');
    const searchTermSpan = document.getElementById('ig-search-term');
    const searchInput = document.getElementById('ig-search-input');
    const clearBtn = document.getElementById('ig-search-clear');

    if (!grid) return; // Not on home page

    let debounceTimer;

    // Initial load
    fetchPosts('/api/instagram/posts');

    // Search input listener
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        
        // Show/hide clear button
        clearBtn.style.display = query.length > 0 ? 'block' : 'none';

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            if (query.length > 0) {
                fetchPosts(`/api/instagram/search?q=${encodeURIComponent(query)}`, query);
            } else {
                fetchPosts('/api/instagram/posts');
            }
        }, 500); // 500ms debounce
    });

    // Clear search
    clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        clearBtn.style.display = 'none';
        fetchPosts('/api/instagram/posts');
    });

    function fetchPosts(url, query = '') {
        grid.innerHTML = '';
        grid.style.display = 'none';
        emptyState.style.display = 'none';
        loading.style.display = 'block';

        fetch(`${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`)
            .then(res => res.json())
            .then(posts => {
                loading.style.display = 'none';
                
                if (posts.length === 0) {
                    if (query) {
                        searchTermSpan.textContent = query;
                        emptyState.style.display = 'block';
                    } else {
                        // If no posts at all, just hide everything quietly or show a fallback message
                        grid.innerHTML = '<p class="ig-empty">Instagram posts not available.</p>';
                        grid.style.display = 'block';
                    }
                    return;
                }

                grid.style.display = 'grid';
                posts.forEach(post => {
                    grid.appendChild(createPostCard(post));
                });
            })
            .catch(err => {
                console.error('Error fetching Instagram posts:', err);
                loading.style.display = 'none';
                grid.innerHTML = '<p class="ig-empty">Error loading Instagram feed.</p>';
                grid.style.display = 'block';
            });
    }

    function createPostCard(post) {
        const card = document.createElement('a');
        card.href = post.permalink;
        card.target = '_blank';
        card.className = 'ig-post-card';

        // Determine image to show
        let imageUrl = post.media_url;
        if (post.media_type === 'VIDEO' && post.thumbnail_url) {
            imageUrl = post.thumbnail_url;
        }

        // Determine icon based on media type
        let iconHtml = '';
        if (post.media_type === 'VIDEO') {
            iconHtml = '<div class="ig-post-type-icon"><i class="fas fa-play"></i></div>';
        } else if (post.media_type === 'CAROUSEL_ALBUM') {
            iconHtml = '<div class="ig-post-type-icon"><i class="fas fa-clone"></i></div>';
        }

        // Format Date
        const dateStr = post.timestamp ? new Date(post.timestamp).toLocaleDateString(undefined, {
            year: 'numeric', month: 'short', day: 'numeric'
        }) : '';

        // Safely handle missing caption
        const caption = post.caption || '';

        card.innerHTML = `
            <div class="ig-post-image-container">
                <img src="${imageUrl}" alt="Instagram Post" class="ig-post-image" loading="lazy">
                ${iconHtml}
            </div>
            <div class="ig-post-content">
                <p class="ig-post-caption">${escapeHtml(caption)}</p>
                <span class="ig-post-date">${dateStr}</span>
            </div>
        `;
        return card;
    }

    // XSS Prevention helper
    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
});

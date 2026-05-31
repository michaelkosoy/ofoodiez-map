document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('ig-posts-grid');
    const loading = document.getElementById('ig-posts-loading');
    const emptyState = document.getElementById('ig-posts-empty');
    const searchTermSpan = document.getElementById('ig-search-term');
    const searchInput = document.getElementById('ig-search-input');
    const clearBtn = document.getElementById('ig-search-clear');

    if (!grid) return; // Not on home page

    // Create Load More button
    const loadMoreBtn = document.createElement('button');
    loadMoreBtn.id = 'ig-load-more';
    loadMoreBtn.className = 'ig-load-more-btn';
    loadMoreBtn.textContent = 'Load More';
    loadMoreBtn.style.display = 'none';
    
    // Insert after the grid
    grid.parentNode.insertBefore(loadMoreBtn, grid.nextSibling);

    let debounceTimer;
    let currentOffset = 0;
    const POSTS_PER_PAGE = 12;
    let currentQuery = '';

    // Initial load
    fetchPosts('/api/instagram/posts', '', 0);

    // Search input listener
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        currentQuery = query;
        
        // Show/hide clear button
        clearBtn.style.display = query.length > 0 ? 'block' : 'none';
        
        // Hide empty state immediately while typing/debouncing
        emptyState.style.display = 'none';
        loadMoreBtn.style.display = 'none';

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            currentOffset = 0;
            if (query.length > 0) {
                fetchPosts(`/api/instagram/search?q=${encodeURIComponent(query)}`, query, 0);
            } else {
                fetchPosts('/api/instagram/posts', '', 0);
            }
        }, 500); // 500ms debounce
    });

    // Clear search
    clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        currentQuery = '';
        clearBtn.style.display = 'none';
        currentOffset = 0;
        fetchPosts('/api/instagram/posts', '', 0);
    });

    // Load More click
    loadMoreBtn.addEventListener('click', () => {
        currentOffset += POSTS_PER_PAGE;
        const base_url = currentQuery ? `/api/instagram/search?q=${encodeURIComponent(currentQuery)}` : '/api/instagram/posts';
        fetchPosts(base_url, currentQuery, currentOffset, true);
    });

    function fetchPosts(url, query = '', offset = 0, append = false) {
        if (!append) {
            grid.innerHTML = '';
            grid.style.display = 'none';
        }
        
        emptyState.style.display = 'none';
        loadMoreBtn.style.display = 'none';
        loading.style.display = 'block';

        const fetchUrl = `${url}${url.includes('?') ? '&' : '?'}offset=${offset}&limit=${POSTS_PER_PAGE}&t=${Date.now()}`;

        fetch(fetchUrl)
            .then(res => res.json())
            .then(data => {
                loading.style.display = 'none';
                
                const posts = data.posts || [];
                
                if (posts.length === 0 && !append) {
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
                
                if (data.has_more) {
                    loadMoreBtn.style.display = 'block';
                }
            })
            .catch(err => {
                console.error('Error fetching Instagram posts:', err);
                loading.style.display = 'none';
                if (!append) {
                    grid.innerHTML = '<p class="ig-empty">Error loading Instagram feed.</p>';
                    grid.style.display = 'block';
                }
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

        // Likes and Comments
        const likes = post.like_count !== undefined ? post.like_count : 0;
        const comments = post.comments_count !== undefined ? post.comments_count : 0;

        // Safely handle missing caption
        const caption = post.caption || '';

        card.innerHTML = `
            <div class="ig-post-image-container">
                <img src="${imageUrl}" alt="Instagram Post" class="ig-post-image" loading="lazy">
                ${iconHtml}
            </div>
            <div class="ig-post-content">
                <p class="ig-post-caption">${escapeHtml(caption)}</p>
                <div class="ig-post-stats">
                    <span><i class="fas fa-heart"></i> ${likes}</span>
                    <span><i class="fas fa-comment"></i> ${comments}</span>
                </div>
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

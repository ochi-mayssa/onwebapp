// Forum JavaScript
(function() {
    // CSRF helper
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');

    // Vote buttons
    document.querySelectorAll('.vote-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            fetch('/forum/post/' + this.dataset.slug + '/vote/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({reaction: this.dataset.vote}),
            })
            .then(r => r.json())
            .then(d => {
                const scoreEl = document.getElementById('score-' + this.dataset.slug);
                if (scoreEl) scoreEl.textContent = d.score;
                document.querySelectorAll('.vote-btn[data-slug="' + this.dataset.slug + '"]').forEach(b => {
                    b.classList.remove('voted', 'voted-down');
                });
            });
        });
    });

    // Bookmark buttons
    document.querySelectorAll('.bookmark-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            fetch('/forum/post/' + this.dataset.slug + '/bookmark/', {
                method: 'POST',
                headers: {'X-CSRFToken': csrftoken, 'Content-Type': 'application/json'},
            })
            .then(r => r.json())
            .then(d => {
                this.innerHTML = d.bookmarked ? 
                    '<i class="fas fa-bookmark me-1"></i>Saved' : 
                    '<i class="far fa-bookmark me-1"></i>Save';
            });
        });
    });

    // Comment reply toggle
    document.querySelectorAll('.reply-toggle').forEach(btn => {
        btn.addEventListener('click', function() {
            const form = document.getElementById('reply-form-' + this.dataset.commentId);
            if (form) form.classList.toggle('d-none');
        });
    });

    document.querySelectorAll('.reply-cancel').forEach(btn => {
        btn.addEventListener('click', function() {
            const form = document.getElementById('reply-form-' + this.dataset.commentId);
            if (form) form.classList.add('d-none');
        });
    });

    // Infinite scroll
    let loading = false;
    let page = 2;
    const scrollContainer = document.querySelector('.forum-infinite-scroll');
    if (scrollContainer) {
        window.addEventListener('scroll', function() {
            if (loading) return;
            const scrollHeight = document.documentElement.scrollHeight;
            const scrollTop = window.scrollY;
            const clientHeight = document.documentElement.clientHeight;
            
            if (scrollTop + clientHeight >= scrollHeight - 400) {
                loading = true;
                const loader = document.createElement('div');
                loader.className = 'forum-loading';
                document.querySelector('.forum-content-area').appendChild(loader);
                
                fetch(window.location.pathname + '?page=' + page, {
                    headers: {'X-Requested-With': 'XMLHttpRequest'}
                })
                .then(r => r.text())
                .then(html => {
                    loader.remove();
                    if (html.trim()) {
                        scrollContainer.insertAdjacentHTML('beforeend', html);
                        page++;
                        loading = false;
                    }
                });
            }
        });
    }

    // Follow user
    document.querySelectorAll('.follow-user-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            fetch('/forum/user/' + this.dataset.username + '/follow/', {
                method: 'POST',
                headers: {'X-CSRFToken': csrftoken, 'Content-Type': 'application/json'},
            })
            .then(r => r.json())
            .then(d => {
                if (d.following) {
                    this.classList.remove('btn-outline-primary');
                    this.classList.add('btn-primary');
                    this.innerHTML = '<i class="fas fa-user-check me-1"></i>Following';
                } else {
                    this.classList.remove('btn-primary');
                    this.classList.add('btn-outline-primary');
                    this.innerHTML = '<i class="fas fa-user-plus me-1"></i>Follow';
                }
            });
        });
    });

    // Follow category
    document.querySelectorAll('.follow-category-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            fetch('/forum/category/' + this.dataset.slug + '/follow/', {
                method: 'POST',
                headers: {'X-CSRFToken': csrftoken, 'Content-Type': 'application/json'},
            })
            .then(r => r.json())
            .then(d => {
                if (d.following) {
                    this.classList.remove('btn-outline-primary');
                    this.classList.add('btn-primary');
                    this.innerHTML = '<i class="fas fa-check me-1"></i>Following';
                } else {
                    this.classList.remove('btn-primary');
                    this.classList.add('btn-outline-primary');
                    this.innerHTML = '<i class="fas fa-plus me-1"></i>Follow';
                }
            });
        });
    });
})();
// Navigation mega-menu enhancements and small UX helpers
(function(){
  // Handle dropdown hover for mega menus on desktop
  const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const dropdowns = document.querySelectorAll('.dropdown-mega');
  if (!isTouch) {
    dropdowns.forEach(dd => {
      dd.addEventListener('mouseenter', () => {
        const toggle = dd.querySelector('[data-bs-toggle="dropdown"]');
        if (toggle) {
          const dropdown = new bootstrap.Dropdown(toggle);
          dropdown.show();
        }
      });
      dd.addEventListener('mouseleave', () => {
        const toggle = dd.querySelector('[data-bs-toggle="dropdown"]');
        if (toggle) {
          const dropdown = new bootstrap.Dropdown(toggle);
          dropdown.hide();
        }
      });
    });
  }

  // Simple search button click demo
  const searchBtn = document.getElementById('navSearchBtn');
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      alert('Search coming soon');
    });
  }
})();
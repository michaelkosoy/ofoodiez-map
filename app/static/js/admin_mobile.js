/* Admin panel on phones: the menu drawer, and the labels the card layout shows
   next to each value (see admin_mobile.css). */

function toggleSidebar(force) {
    const sidebar = document.getElementById('sidebar');
    const open = sidebar.classList.toggle('open', force);
    document.getElementById('sidebar-overlay').classList.toggle('open', open);
    document.querySelector('.mobile-menu-btn').setAttribute('aria-expanded', open);
}

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') toggleSidebar(false);
});

function setLabel(cell, label) {
    if (cell.getAttribute('data-label') !== label) cell.setAttribute('data-label', label);
}

function labelTableCells() {
    document.querySelectorAll('.tabulator').forEach(function (table) {
        const titles = Array.from(table.querySelectorAll('.tabulator-headers .tabulator-col')).map(function (col) {
            const title = col.querySelector('.tabulator-col-title');
            return title ? title.textContent.trim() : '';
        });
        table.querySelectorAll('.tabulator-row').forEach(function (row) {
            row.querySelectorAll(':scope > .tabulator-cell').forEach(function (cell, i) {
                setLabel(cell, titles[i] || '');
            });
        });
    });

    document.querySelectorAll('table.ttable, #cvr-table, .codes-table').forEach(function (table) {
        const titles = Array.from(table.querySelectorAll('thead th')).map(function (th) {
            return th.textContent.trim();
        });
        table.querySelectorAll('tbody tr').forEach(function (row) {
            Array.from(row.children).forEach(function (cell, i) {
                setLabel(cell, cell.colSpan > 1 ? '' : (titles[i] || ''));
            });
        });
    });
}

let labelFrame = null;
new MutationObserver(function () {
    if (labelFrame) return;
    labelFrame = requestAnimationFrame(function () {
        labelFrame = null;
        labelTableCells();
    });
}).observe(document.body, { childList: true, subtree: true });
labelTableCells();

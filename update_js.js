const fs = require('fs');
let code = fs.readFileSync('app/static/js/main.js', 'utf8');

const positionHelper = `
function updateDropdownPosition(event) {
    if (window.innerWidth <= 768) {
        const selectElement = event.target;
        const choicesContainer = selectElement.closest('.choices');
        if (choicesContainer) {
            const rect = choicesContainer.getBoundingClientRect();
            document.documentElement.style.setProperty('--dropdown-top', (rect.bottom + 4) + 'px');
            document.documentElement.style.setProperty('--dropdown-left', rect.left + 'px');
            document.documentElement.style.setProperty('--dropdown-width', rect.width + 'px');
        }
    }
}
`;

// Insert the helper near the top, after DOMContentLoaded
code = code.replace("document.addEventListener('DOMContentLoaded', () => {", "document.addEventListener('DOMContentLoaded', () => {\n" + positionHelper);

// Inject into populateDaysFilter
code = code.replace(
    "daysSelect.addEventListener('change', (e) => {",
    "daysSelect.addEventListener('showDropdown', updateDropdownPosition);\n        daysSelect.addEventListener('change', (e) => {"
);

// Inject into populateFilter
code = code.replace(
    "filterSelect.addEventListener('change', function (e) {",
    "filterSelect.addEventListener('showDropdown', updateDropdownPosition);\n        filterSelect.addEventListener('change', function (e) {"
);

fs.writeFileSync('app/static/js/main.js', code);
console.log("Updated main.js with robust event listeners attached directly to the select elements!");

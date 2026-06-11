// Pop-up Events Calendar Controller
document.addEventListener('DOMContentLoaded', function () {
    // Check if event data is loaded
    if (typeof POPUP_EVENTS === 'undefined' || !Array.isArray(POPUP_EVENTS)) {
        console.warn('⚠️ POPUP_EVENTS is not defined or is not an array.');
        return;
    }

    // Expand events with multiple dates into separate event objects
    let EXPANDED_EVENTS = [];
    POPUP_EVENTS.forEach(event => {
        if (event.date && event.date.includes('|')) {
            const dates = event.date.split('|').map(d => d.trim());
            dates.forEach(d => {
                EXPANDED_EVENTS.push({ ...event, date: d });
            });
        } else {
            EXPANDED_EVENTS.push(event);
        }
    });

    // Localized month names
    const MONTH_NAMES = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];

    const SHORT_MONTHS = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ];

    // Initialize state
    // We base the default date on the current local time or the first upcoming event if we are out of range
    const today = new Date();
    let currentYear = today.getFullYear();
    let currentMonth = today.getMonth(); // 0-11
    let selectedDateKey = null;

    // DOM Elements
    const calendarTitle = document.querySelector('.calendar-title');
    const calendarDays = document.querySelector('.calendar-days');
    const prevBtn = document.querySelector('.calendar-prev-btn');
    const nextBtn = document.querySelector('.calendar-next-btn');
    const detailsContainer = document.querySelector('.details-card');
    const upcomingListContainer = document.querySelector('.upcoming-events-list');

    // Initialize the calendar
    function init() {
        // Render initial UI components
        renderCalendar(currentYear, currentMonth);
        renderUpcomingEventsList();

        // Register header button events
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                currentMonth--;
                if (currentMonth < 0) {
                    currentMonth = 11;
                    currentYear--;
                }
                renderCalendar(currentYear, currentMonth);
                highlightActiveDayInGrid();
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                currentMonth++;
                if (currentMonth > 11) {
                    currentMonth = 0;
                    currentYear++;
                }
                renderCalendar(currentYear, currentMonth);
                highlightActiveDayInGrid();
            });
        }
    }

    // Render Calendar grid for a given year & month
    function renderCalendar(year, month) {
        if (!calendarDays || !calendarTitle) return;

        // Set header month/year title
        calendarTitle.textContent = `${MONTH_NAMES[month]} ${year}`;

        // Clear previous days
        calendarDays.innerHTML = '';

        // First day of the month index (0 = Sunday, 1 = Monday, ...)
        const firstDayIdx = new Date(year, month, 1).getDay();

        // Total days in the month
        const totalDays = new Date(year, month + 1, 0).getDate();

        // 1. Add empty cells for padding before the 1st of the month
        for (let i = 0; i < firstDayIdx; i++) {
            const emptyCell = document.createElement('div');
            emptyCell.className = 'calendar-day-cell empty';
            calendarDays.appendChild(emptyCell);
        }

        // 2. Add days of the month
        const todayYear = today.getFullYear();
        const todayMonth = today.getMonth();
        const todayDate = today.getDate();

        for (let day = 1; day <= totalDays; day++) {
            const cell = document.createElement('div');
            cell.className = 'calendar-day-cell';
            cell.textContent = day;

            // Generate date string format: YYYY-MM-DD
            const monthStr = String(month + 1).padStart(2, '0');
            const dayStr = String(day).padStart(2, '0');
            const dateKey = `${year}-${monthStr}-${dayStr}`;
            cell.dataset.date = dateKey;

            // Check if day is today
            if (year === todayYear && month === todayMonth && day === todayDate) {
                cell.classList.add('today');
            }

            // Check if there is a pop-up on this day
            const dayEvents = EXPANDED_EVENTS.filter(e => e.date === dateKey);
            if (dayEvents.length > 0) {
                cell.classList.add('has-popup');
            }

            // Click listener for date cell
            cell.addEventListener('click', () => {
                selectDay(dateKey, dayEvents, cell);
            });

            calendarDays.appendChild(cell);
        }
    }

    // Select a specific day
    function selectDay(dateKey, events, cellElement = null) {
        selectedDateKey = dateKey;

        // Remove active class from all cells
        document.querySelectorAll('.calendar-day-cell').forEach(c => {
            c.classList.remove('active');
        });

        // Add active class to clicked cell
        if (cellElement) {
            cellElement.classList.add('active');
        } else {
            // Find cell element by data attribute if not passed
            const cell = document.querySelector(`.calendar-day-cell[data-date="${dateKey}"]`);
            if (cell) cell.classList.add('active');
        }

        // Update selected details card
        showEventDetails(events, dateKey);

        // Highlight matching list items in the sidebar list
        document.querySelectorAll('.upcoming-event-item').forEach(item => {
            if (item.dataset.date === dateKey) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    // Render event details in sidebar card
    function showEventDetails(events, dateKey) {
        if (!detailsContainer) return;

        if (!events || events.length === 0) {
            detailsContainer.classList.add('hidden');
            return;
        }

        detailsContainer.classList.remove('hidden');

        // Render details of the events on this day (assuming 1 event per day, but mapping if multiple exist)
        let html = '';
        events.forEach((event, idx) => {
            // Parse event date
            const dateParts = event.date.split('-');
            const dateObj = new Date(parseInt(dateParts[0]), parseInt(dateParts[1]) - 1, parseInt(dateParts[2]));
            const dayOfWeek = dateObj.toLocaleDateString('en-US', { weekday: 'long' });
            const monthName = dateObj.toLocaleDateString('en-US', { month: 'long' });
            const dayNum = dateObj.getDate();
            const formattedDate = `${dayOfWeek}, ${monthName} ${dayNum}`;

            html += `
                ${idx > 0 ? '<div style="border-top: 3px dashed rgba(90, 58, 49, 0.3); margin: 20px 0; padding-top: 15px;"></div>' : ''}
                <div class="details-card-header">
                    <h4 class="details-card-title">${event.title}</h4>
                    ${idx === 0 ? '<button class="details-close-btn" aria-label="Close details">&times;</button>' : ''}
                </div>
                
                <div class="details-meta">
                    <div class="details-meta-item">
                        <i class="far fa-calendar-alt"></i>
                        <span>${formattedDate} &nbsp;|&nbsp; <i class="far fa-clock"></i> ${event.time}</span>
                    </div>
                    <div class="details-meta-item">
                        <i class="fas fa-map-marker-alt"></i>
                        ${event.location_link ? `
                            <a href="${event.location_link}" target="_blank" style="text-decoration: underline; color: inherit;">
                                ${event.location}
                            </a>
                        ` : `<span>${event.location}</span>`}
                    </div>
                    ${event.instagram_username ? `
                        <div class="details-meta-item">
                            <i class="fab fa-instagram"></i>
                            <a href="${event.instagram_link || '#'}" target="_blank" style="color: var(--accent-color); font-weight: 700; text-decoration: underline;">
                                ${event.instagram_username}
                            </a>
                        </div>
                    ` : ''}
                </div>
                
                <p class="details-description">${event.description}</p>
            `;
        });

        detailsContainer.innerHTML = html;

        // Bind close button handler
        const closeBtn = detailsContainer.querySelector('.details-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                detailsContainer.classList.add('hidden');
                document.querySelectorAll('.calendar-day-cell').forEach(c => c.classList.remove('active'));
                document.querySelectorAll('.upcoming-event-item').forEach(item => item.classList.remove('active'));
                selectedDateKey = null;
            });
        }
    }

    // Render chronological upcoming events list in sidebar
    function renderUpcomingEventsList() {
        if (!upcomingListContainer) return;

        upcomingListContainer.innerHTML = '';

        // Sort ORIGINAL events chronologically by their first date
        const sortedEvents = [...POPUP_EVENTS].sort((a, b) => {
            const dateA = a.date.split('|')[0].trim();
            const dateB = b.date.split('|')[0].trim();
            return new Date(dateA) - new Date(dateB);
        });

        if (sortedEvents.length === 0) {
            upcomingListContainer.innerHTML = `
                <div style="text-align: center; padding: 20px 0; color: #777; font-style: italic; font-size: 0.9rem;">
                    No upcoming pop-ups scheduled.
                </div>
            `;
            return;
        }

        sortedEvents.forEach(event => {
            const item = document.createElement('div');
            item.className = 'upcoming-event-item';
            
            const dateStrings = event.date.split('|').map(d => d.trim());
            const firstDateStr = dateStrings[0];
            item.dataset.date = firstDateStr; // Use first date for data matching

            // Parse FIRST date to extract day number and short month name for the badge
            const dateParts = firstDateStr.split('-');
            const firstDateObj = new Date(parseInt(dateParts[0]), parseInt(dateParts[1]) - 1, parseInt(dateParts[2]));
            const dayNum = firstDateObj.getDate();
            const shortMonth = SHORT_MONTHS[firstDateObj.getMonth()];

            // Format all dates for the meta description
            const formattedAllDates = dateStrings.map(d => {
                const parts = d.split('-');
                const obj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                return `${obj.getDate()} ${SHORT_MONTHS[obj.getMonth()]}`;
            }).join(', ');

            item.innerHTML = `
                <div class="event-date-badge">
                    <span class="badge-day">${dayNum}</span>
                    <span class="badge-month">${shortMonth}</span>
                </div>
                <div class="event-item-info">
                    <h5 class="event-item-title">${event.title}</h5>
                    <div class="event-item-meta">
                        ${dateStrings.length > 1 ? `<span style="display:block; margin-bottom: 4px; color: var(--accent-color); font-weight: 600;"><i class="far fa-calendar-alt"></i> ${formattedAllDates}</span>` : ''}
                        <span><i class="far fa-clock"></i> ${event.time}</span>
                        <span><i class="fas fa-map-marker-alt"></i> ${event.location.split(',')[0]}</span>
                    </div>
                </div>
            `;

            // Click event list item navigates to the FIRST date of the event
            item.addEventListener('click', () => {
                currentYear = firstDateObj.getFullYear();
                currentMonth = firstDateObj.getMonth();

                // Re-render calendar to the correct month and select the day
                renderCalendar(currentYear, currentMonth);

                const dayEvents = EXPANDED_EVENTS.filter(e => e.date === firstDateStr);
                selectDay(firstDateStr, dayEvents);

                // Smooth scroll to the details card if in mobile/stacked view
                if (window.innerWidth < 1024) {
                    detailsContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            });

            upcomingListContainer.appendChild(item);
        });
    }

    // Keep active day circled if we switch months and come back
    function highlightActiveDayInGrid() {
        if (!selectedDateKey) return;
        const activeCell = document.querySelector(`.calendar-day-cell[data-date="${selectedDateKey}"]`);
        if (activeCell) {
            activeCell.classList.add('active');
        }
    }

    // Start everything
    init();
});

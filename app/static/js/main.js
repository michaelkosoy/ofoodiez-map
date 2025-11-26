let map;
let allPlaces = [];
let markers = [];

async function initMap() {
    const { Map } = await google.maps.importLibrary("maps");
    const { AdvancedMarkerElement } = await google.maps.importLibrary("marker");

    // Custom map style to match the "premium" look (simplified version of Snazzy Maps "Ultra Light with Labels")
    const mapStyle = [
        {
            "featureType": "water",
            "elementType": "geometry",
            "stylers": [{ "color": "#e9e9e9" }, { "lightness": 17 }]
        },
        {
            "featureType": "landscape",
            "elementType": "geometry",
            "stylers": [{ "color": "#f5f5f5" }, { "lightness": 20 }]
        },
        {
            "featureType": "road.highway",
            "elementType": "geometry.fill",
            "stylers": [{ "color": "#ffffff" }, { "lightness": 17 }]
        },
        {
            "featureType": "road.highway",
            "elementType": "geometry.stroke",
            "stylers": [{ "color": "#ffffff" }, { "lightness": 29 }, { "weight": 0.2 }]
        },
        {
            "featureType": "road.arterial",
            "elementType": "geometry",
            "stylers": [{ "color": "#ffffff" }, { "lightness": 18 }]
        },
        {
            "featureType": "road.local",
            "elementType": "geometry",
            "stylers": [{ "color": "#ffffff" }, { "lightness": 16 }]
        },
        {
            "featureType": "poi",
            "elementType": "geometry",
            "stylers": [{ "color": "#f5f5f5" }, { "lightness": 21 }]
        },
        {
            "featureType": "poi.park",
            "elementType": "geometry",
            "stylers": [{ "color": "#dedede" }, { "lightness": 21 }]
        },
        {
            "elementType": "labels.text.stroke",
            "stylers": [{ "visibility": "on" }, { "color": "#ffffff" }, { "lightness": 16 }]
        },
        {
            "elementType": "labels.text.fill",
            "stylers": [{ "saturation": 36 }, { "color": "#333333" }, { "lightness": 40 }]
        },
        {
            "elementType": "labels.icon",
            "stylers": [{ "visibility": "off" }]
        },
        {
            "featureType": "transit",
            "elementType": "geometry",
            "stylers": [{ "color": "#f2f2f2" }, { "lightness": 19 }]
        },
        {
            "featureType": "administrative",
            "elementType": "geometry.fill",
            "stylers": [{ "color": "#fefefe" }, { "lightness": 20 }]
        },
        {
            "featureType": "administrative",
            "elementType": "geometry.stroke",
            "stylers": [{ "color": "#fefefe" }, { "lightness": 17 }, { "weight": 1.2 }]
        }
    ];

    map = new Map(document.getElementById("map"), {
        center: { lat: 32.075, lng: 34.775 },
        zoom: 14,
        mapId: "DEMO_MAP_ID", // Required for AdvancedMarkerElement, using demo ID
        styles: mapStyle,
        disableDefaultUI: true,
        zoomControl: false, // We can add custom controls if needed
    });



    fetchPlaces();

    // Auto-focus on user location
    showUserLocation();
}

function fetchPlaces() {
    fetch('/api/places')
        .then(response => response.json())
        .then(data => {
            allPlaces = data;
            populateFilter(allPlaces);
            renderPlaceList(allPlaces);
            addMarkers(allPlaces);
        })
        .catch(error => console.error('Error loading places:', error));
}

let infoWindow;

function populateFilter(places) {
    const filterSelect = document.getElementById('category-filter');
    const categories = new Set(places.map(p => p.Category).filter(c => c));

    // Define the priority order
    const priorityOrder = [
        "Until 19:00",
        "until 19:30",
        "Until 20:00",
        "After 20:00",
        "WEEKENDS",
        "Not TLV"
    ];

    // Hebrew mappings
    const hebrewLabels = {
        "Until 19:00": "עד 19:00",
        "until 19:30": "עד 19:30",
        "Until 20:00": "עד 20:00",
        "After 20:00": "אחרי 20:00",
        "WEEKENDS": "סופ״ש",
        "Not TLV": "מחוץ לת״א"
    };

    // Convert to array and sort
    const sortedCategories = Array.from(categories).sort((a, b) => {
        const indexA = priorityOrder.findIndex(p => p.toLowerCase() === a.toLowerCase());
        const indexB = priorityOrder.findIndex(p => p.toLowerCase() === b.toLowerCase());

        // If both are in priority list, sort by priority
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        // If only A is in priority list, A comes first
        if (indexA !== -1) return -1;
        // If only B is in priority list, B comes first
        if (indexB !== -1) return 1;

        // Otherwise sort alphabetically
        return a.localeCompare(b);
    });

    // Clear existing options (except "All Times" if we want to keep it or replace it)
    filterSelect.innerHTML = '<option value="all">כל השעות</option>';

    sortedCategories.forEach(category => {
        const option = document.createElement('option');
        option.value = category; // Keep the original value for filtering logic
        option.textContent = hebrewLabels[category] || category; // Show Hebrew label
        filterSelect.appendChild(option);
    });
}

window.filterPlaces = () => {
    const selectedCategory = document.getElementById('category-filter').value;

    // Filter places
    const filteredPlaces = selectedCategory === 'all'
        ? allPlaces
        : allPlaces.filter(p => p.Category === selectedCategory);

    // Update List
    renderPlaceList(filteredPlaces);

    // Update Markers
    updateMarkers(filteredPlaces);
};

async function updateMarkers(places) {
    // Clear existing markers
    markers.forEach(m => m.marker.map = null);
    markers = [];

    // Add new markers
    addMarkers(places);
}

async function addMarkers(places) {
    const { AdvancedMarkerElement, PinElement } = await google.maps.importLibrary("marker");
    const { InfoWindow } = await google.maps.importLibrary("maps");

    if (!infoWindow) {
        infoWindow = new InfoWindow();
    }

    places.forEach(place => {
        if (place.Latitude && place.Longitude) {
            // Create a custom pin
            const pin = new PinElement({
                background: "#FF6B6B",
                borderColor: "#FFFFFF",
                glyphColor: "#FFFFFF",
                scale: 1.1,
            });

            const marker = new AdvancedMarkerElement({
                map: map,
                position: { lat: place.Latitude, lng: place.Longitude },
                title: place.Name,
                content: pin.element,
            });

            marker.addListener("click", () => {
                showPlaceDetails(place);
                highlightMarker(place.Name);

                // Ensure smooth transition
                map.setCenter(marker.position);
                map.setZoom(16);

                // Show InfoWindow
                const contentString = `
                    <div class="info-window-content">
                        <h3 style="margin: 0 0 5px 0; color: #333;">${place.Name}</h3>
                        ${place.Address ? `<p style="margin: 0 0 5px 0; font-size: 13px; color: #888;"><i class="fas fa-map-marker-alt"></i> ${place.Address}</p>` : ''}
                        <p style="margin: 5px 0 0 0; font-size: 14px; color: #666;">${place.Description || place.Category}</p>
                        ${place.InstagramURL ? `<a href="${place.InstagramURL}" target="_blank" style="display: inline-block; margin-top: 8px; color: #E1306C; text-decoration: none; font-size: 24px;"><i class="fab fa-instagram"></i></a>` : ''}
                    </div>
                `;
                infoWindow.setContent(contentString);
                infoWindow.open({
                    anchor: marker,
                    map,
                });
            });

            markers.push({ name: place.Name, marker: marker });
        }
    });
}

function highlightMarker(placeName) {
    markers.forEach(m => {
        if (m.name === placeName) {
            // Highlight - Blue color
            const pin = new google.maps.marker.PinElement({
                background: "#2E86DE",
                borderColor: "#FFFFFF",
                glyphColor: "#FFFFFF",
                scale: 1.3,
            });
            m.marker.content = pin.element;
            m.marker.zIndex = 999;
        } else {
            // Reset - Default Red
            const pin = new google.maps.marker.PinElement({
                background: "#FF6B6B",
                borderColor: "#FFFFFF",
                glyphColor: "#FFFFFF",
                scale: 1.1,
            });
            m.marker.content = pin.element;
            m.marker.zIndex = null;
        }
    });
}

const sidebarContent = document.getElementById('sidebar-content');

function renderPlaceList(places) {
    const listHtml = `
        <ul class="place-list">
            ${places.map(place => `
                <li class="place-list-item" onclick="handlePlaceClick('${place.Name.replace(/'/g, "\\'")}')">
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <div>
                            <h3>${place.Name}</h3>
                        </div>
                        ${place.InstagramURL ? `<a href="${place.InstagramURL}" target="_blank" onclick="event.stopPropagation()" style="color: #E1306C; font-size: 20px; margin-left: 10px;"><i class="fab fa-instagram"></i></a>` : ''}
                    </div>
                </li>
            `).join('')}
        </ul>
    `;
    sidebarContent.innerHTML = listHtml;
}

window.handlePlaceClick = (placeName) => {
    const place = allPlaces.find(p => p.Name === placeName);
    if (place) {
        highlightMarker(placeName);

        // Find marker and trigger its click event first
        const markerObj = markers.find(m => m.name === placeName);
        if (markerObj) {
            map.setCenter(markerObj.marker.position);
            map.setZoom(16);

            // Trigger marker click to show InfoWindow
            // Use setTimeout to ensure map has time to pan/zoom before opening InfoWindow
            setTimeout(() => {
                google.maps.event.trigger(markerObj.marker, 'click');
            }, 300);
        }

        // Show details in sidebar after a brief delay
        setTimeout(() => {
            showPlaceDetails(place);
        }, 100);
    }
};

window.showList = () => {
    renderPlaceList(allPlaces);
};

function showPlaceDetails(place) {
    let imageHtml = '';
    if (place.ImageURL) {
        imageHtml = `<img src="${place.ImageURL}" alt="${place.Name}" class="place-image">`;
    }

    sidebarContent.innerHTML = `
        <div class="place-details">
            <button class="back-button" onclick="showList()">
                ← Back to list
            </button>
            <div class="place-card">
                ${imageHtml}
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2>${place.Name}</h2>
                    ${place.InstagramURL ? `<a href="${place.InstagramURL}" target="_blank" style="color: #E1306C; font-size: 24px;"><i class="fab fa-instagram"></i></a>` : ''}
                </div>
                <p class="place-description">${place.Description}</p>
            </div>
        </div>
    `;
}

// Mobile: Make sidebar draggable
if (window.innerWidth <= 768) {
    const sidebar = document.getElementById('sidebar');
    const sidebarHeader = document.querySelector('.sidebar-header');

    let startY = 0;
    let currentY = 0;
    let isDragging = false;
    let startTranslateY = 0;

    // Calculate the collapsed and expanded positions
    // Collapsed: translateY(calc(100% - 260px)) -> we need the pixel value
    // Expanded: translateY(0)

    // Helper to get current transform Y value
    const getTranslateY = (element) => {
        const style = window.getComputedStyle(element);
        const matrix = new WebKitCSSMatrix(style.transform);
        return matrix.m42;
    };

    sidebarHeader.addEventListener('touchstart', (e) => {
        startY = e.touches[0].clientY;
        isDragging = true;
        startTranslateY = getTranslateY(sidebar);

        // Disable transition during drag
        sidebar.classList.add('is-dragging');
    }, { passive: true });

    sidebarHeader.addEventListener('touchmove', (e) => {
        if (!isDragging) return;

        const currentTouchY = e.touches[0].clientY;
        const diff = currentTouchY - startY;
        let newTranslateY = startTranslateY + diff;

        // Limit the drag range
        // Max up: 0 (expanded)
        // Max down: window.innerHeight - 100 (collapsed state approx)
        // Note: The CSS defines collapsed as calc(100% - 260px)

        if (newTranslateY < 0) newTranslateY = 0; // Don't drag past top

        sidebar.style.transform = `translateY(${newTranslateY}px)`;
    }, { passive: true });

    sidebarHeader.addEventListener('touchend', (e) => {
        isDragging = false;
        sidebar.classList.remove('is-dragging');
        sidebar.style.transform = ''; // Clear inline style to let CSS take over

        const currentTouchY = e.changedTouches[0].clientY;
        const diff = currentTouchY - startY;

        // Threshold for snapping
        if (Math.abs(diff) > 50) {
            if (diff > 0) {
                // Dragged down -> Collapse
                sidebar.classList.remove('expanded');
            } else {
                // Dragged up -> Expand
                sidebar.classList.add('expanded');
            }
        } else {
            // If moved less than threshold, toggle based on click/tap
            if (diff === 0) {
                sidebar.classList.toggle('expanded');
            } else {
                // Revert to nearest state
                if (sidebar.classList.contains('expanded')) {
                    sidebar.classList.add('expanded');
                } else {
                    sidebar.classList.remove('expanded');
                }
            }
        }
    });

    // Close sidebar when clicking on map
    document.getElementById('map').addEventListener('click', () => {
        sidebar.classList.remove('expanded');
    });
}

// User Location Logic
let userMarker = null;

async function showUserLocation() {
    if (!navigator.geolocation) {
        alert("Geolocation is not supported by your browser");
        return;
    }

    const btn = document.getElementById('locate-btn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; // Loading state

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            const { latitude, longitude } = position.coords;
            const pos = { lat: latitude, lng: longitude };

            const { AdvancedMarkerElement } = await google.maps.importLibrary("marker");

            // Create custom marker element
            const markerContent = document.createElement('div');
            markerContent.className = 'user-location-marker';

            const pulse = document.createElement('div');
            pulse.className = 'user-location-pulse';
            markerContent.appendChild(pulse);

            // Remove existing user marker if any
            if (userMarker) {
                userMarker.map = null;
            }

            // Create new marker
            userMarker = new AdvancedMarkerElement({
                map: map,
                position: pos,
                content: markerContent,
                title: "Your Location"
            });

            // Center map
            map.setCenter(pos);
            map.setZoom(17);

            // Reset button icon
            btn.innerHTML = '<i class="fas fa-location-arrow"></i>';
        },
        () => {
            alert("Error: The Geolocation service failed.");
            btn.innerHTML = '<i class="fas fa-location-arrow"></i>';
        }
    );
}

initMap();

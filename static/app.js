const state = {
    activeSection: "live",

    matches: {
        live: [],
        upcoming: [],
        finished: []
    },

    search: {
        active: false,
        query: "",
        suggestions: []
    }
};


document.addEventListener(
    "DOMContentLoaded",
    () => {
        setupTabs();
        setupSearch();
        loadMatches();

        // Refresh the normal match feed every 60 seconds.
        setInterval(
            loadMatches,
            60 * 1000
        );
    }
);


/* =========================
   TABS
   ========================= */

function setupTabs() {
    const tabs =
        document.querySelectorAll(".tab");

    tabs.forEach((tab) => {
        tab.addEventListener(
            "click",
            () => {
                const section =
                    tab.dataset.section;

                if (!section) {
                    return;
                }

                switchSection(section);
            }
        );
    });
}


function switchSection(section) {
    state.activeSection = section;

    document
        .querySelectorAll(".tab")
        .forEach((tab) => {
            tab.classList.toggle(
                "active",
                tab.dataset.section === section
            );
        });

    document
        .querySelectorAll(".match-section")
        .forEach((element) => {
            element.classList.toggle(
                "active-section",
                element.id === `${section}Section`
            );
        });
}


/* =========================
   SEARCH SETUP
   ========================= */

function setupSearch() {
    const input =
        document.getElementById("matchSearch");

    const clearButton =
        document.getElementById("clearSearch");

    const closeButton =
        document.getElementById("closeSearch");

    if (!input) {
        return;
    }


    let timer = null;


    input.addEventListener(
        "input",
        () => {
            const query =
                input.value.trim();

            updateClearButton(
                query
            );

            clearTimeout(timer);

            timer = setTimeout(
                () => {
                    handleSearchInput(
                        query
                    );
                },
                150
            );
        }
    );


    input.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Enter"
            ) {
                event.preventDefault();

                const query =
                    input.value.trim();

                if (query) {
                    performSearch(query);
                }

                return;
            }


            if (
                event.key === "Escape"
            ) {
                hideSuggestions();
                return;
            }
        }
    );


    input.addEventListener(
        "focus",
        () => {
            const query =
                input.value.trim();

            if (query) {
                handleSearchInput(
                    query
                );
            }
        }
    );


    if (clearButton) {
        clearButton.addEventListener(
            "click",
            () => {
                clearSearch();
            }
        );
    }


    if (closeButton) {
        closeButton.addEventListener(
            "click",
            () => {
                clearSearch();
            }
        );
    }


    document.addEventListener(
        "click",
        (event) => {

            const searchSection =
                document.querySelector(
                    ".search-section"
                );

            if (!searchSection) {
                return;
            }

            if (
                !searchSection.contains(
                    event.target
                )
            ) {
                hideSuggestions();
            }
        }
    );
}


/* =========================
   SEARCH INPUT
   ========================= */

async function handleSearchInput(query) {
    if (!query) {
        hideSuggestions();
        return;
    }

    await loadSearchData(
        query,
        false
    );
}


async function performSearch(query) {
    if (!query) {
        return;
    }

    hideSuggestions();

    await loadSearchData(
        query,
        true
    );
}


/* =========================
   SEARCH API
   ========================= */

async function loadSearchData(
    query,
    showResults
) {
    try {
        const response =
            await fetch(
                `/api/search?q=${encodeURIComponent(query)}`,
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    },
                    cache: "no-store"
                }
            );


        if (!response.ok) {
            throw new Error(
                `Search request failed: ${response.status}`
            );
        }


        const data =
            await response.json();


        if (!data.ok) {
            throw new Error(
                data.error ||
                "Search failed"
            );
        }


        state.search.query =
            query;

        state.search.suggestions =
            Array.isArray(
                data.suggestions
            )
                ? data.suggestions
                : [];


        if (
            document.activeElement ===
            document.getElementById(
                "matchSearch"
            )
        ) {
            renderSuggestions(
                state.search.suggestions
            );
        }


        if (showResults) {
            renderSearchResults(
                data
            );
        }

    } catch (error) {
        console.error(
            "Search error:",
            error
        );


        if (showResults) {
            renderSearchError(
                "Unable to search matches right now."
            );
        }
    }
}


/* =========================
   SUGGESTIONS
   ========================= */

function renderSuggestions(
    suggestions
) {
    const container =
        document.getElementById(
            "suggestions"
        );

    if (!container) {
        return;
    }


    if (
        !Array.isArray(
            suggestions
        ) ||
        suggestions.length === 0
    ) {
        hideSuggestions();
        return;
    }


    container.innerHTML =
        suggestions
            .map(
                (suggestion) => {
                    const safeValue =
                        escapeHtml(
                            suggestion
                        );

                    const firstLetter =
                        escapeHtml(
                            suggestion
                                .charAt(0)
                                .toUpperCase()
                        );

                    return `
                        <button
                            type="button"
                            class="suggestion-item"
                            data-suggestion="${escapeAttribute(
                                suggestion
                            )}"
                            role="option"
                        >
                            <span class="suggestion-type">
                                ${firstLetter}
                            </span>

                            <span>
                                ${safeValue}
                            </span>
                        </button>
                    `;
                }
            )
            .join("");


    container.classList.remove(
        "hidden"
    );


    container
        .querySelectorAll(
            ".suggestion-item"
        )
        .forEach((button) => {

            button.addEventListener(
                "click",
                () => {
                    const value =
                        button.dataset
                            .suggestion;

                    const input =
                        document.getElementById(
                            "matchSearch"
                        );

                    if (input) {
                        input.value =
                            value;
                    }

                    updateClearButton(
                        value
                    );

                    performSearch(
                        value
                    );
                }
            );
        });
}


function hideSuggestions() {
    const container =
        document.getElementById(
            "suggestions"
        );

    if (!container) {
        return;
    }

    container.classList.add(
        "hidden"
    );

    container.innerHTML = "";
}


/* =========================
   CLEAR SEARCH
   ========================= */

function clearSearch() {
    const input =
        document.getElementById(
            "matchSearch"
        );

    if (input) {
        input.value = "";
    }


    state.search.active =
        false;

    state.search.query =
        "";

    state.search.suggestions =
        [];


    updateClearButton("");

    hideSuggestions();

    hideSearchResults();

    showNormalMatches();

    switchSection(
        state.activeSection ||
        "live"
    );
}


function updateClearButton(
    query
) {
    const button =
        document.getElementById(
            "clearSearch"
        );

    if (!button) {
        return;
    }

    button.classList.toggle(
        "hidden",
        !query
    );
}


/* =========================
   LOAD NORMAL MATCHES
   ========================= */

async function loadMatches() {
    setConnection(
        "loading"
    );


    try {
        const response =
            await fetch(
                "/api/matches",
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    },
                    cache: "no-store"
                }
            );


        if (!response.ok) {
            throw new Error(
                `Server returned ${response.status}`
            );
        }


        const data =
            await response.json();


        if (!data.ok) {
            throw new Error(
                data.error ||
                "Unable to load matches"
            );
        }


        state.matches.live =
            Array.isArray(data.live)
                ? data.live
                : [];


        state.matches.upcoming =
            Array.isArray(data.upcoming)
                ? data.upcoming
                : [];


        state.matches.finished =
            Array.isArray(data.finished)
                ? data.finished
                : [];


        renderCounts(
            data.counts || {}
        );


        renderMatches(
            "live",
            state.matches.live
        );


        renderMatches(
            "upcoming",
            state.matches.upcoming
        );


        renderMatches(
            "finished",
            state.matches.finished
        );


        updateLastUpdated(
            data.updated_at
        );


        renderErrors(
            data.errors || []
        );


        setConnection(
            "online"
        );

    } catch (error) {
        console.error(
            "CrixData API error:",
            error
        );


        setConnection(
            "offline"
        );


        showGlobalError(
            "Unable to load cricket data right now. Please try again."
        );


        renderMatches(
            "live",
            []
        );


        renderMatches(
            "upcoming",
            []
        );


        renderMatches(
            "finished",
            []
        );
    }
}


/* =========================
   CONNECTION
   ========================= */

function setConnection(
    status
) {
    const dot =
        document.getElementById(
            "connectionDot"
        );

    const text =
        document.getElementById(
            "connectionText"
        );


    if (!dot || !text) {
        return;
    }


    dot.classList.remove(
        "online",
        "offline"
    );


    if (
        status === "online"
    ) {
        dot.classList.add(
            "online"
        );

        text.textContent =
            "Live connection";

        return;
    }


    if (
        status === "offline"
    ) {
        dot.classList.add(
            "offline"
        );

        text.textContent =
            "Connection error";

        return;
    }


    text.textContent =
        "Updating...";
}


/* =========================
   NORMAL COUNTS
   ========================= */

function renderCounts(
    counts
) {
    document.getElementById(
        "liveCount"
    ).textContent =
        safeNumber(
            counts.live
        );


    document.getElementById(
        "upcomingCount"
    ).textContent =
        safeNumber(
            counts.upcoming
        );


    document.getElementById(
        "finishedCount"
    ).textContent =
        safeNumber(
            counts.finished
        );
}


/* =========================
   NORMAL MATCH RENDER
   ========================= */

function renderMatches(
    section,
    matches
) {
    const container =
        document.getElementById(
            `${section}Matches`
        );


    if (!container) {
        return;
    }


    if (
        !Array.isArray(matches) ||
        matches.length === 0
    ) {
        container.innerHTML = `
            <div class="empty-state">
                ${emptyMessage(section)}
            </div>
        `;

        return;
    }


    container.innerHTML =
        matches
            .map(
                (match) =>
                    createMatchCard(
                        match,
                        section
                    )
            )
            .join("");
}


/* =========================
   MATCH CARD
   ========================= */

function createMatchCard(
    match,
    section
) {
    const team1 =
        escapeHtml(
            match.team1 ||
            "Team 1"
        );


    const team2 =
        escapeHtml(
            match.team2 ||
            "Team 2"
        );


    const score1 =
        escapeHtml(
            match.team1_score ||
            ""
        );


    const score2 =
        escapeHtml(
            match.team2_score ||
            ""
        );


    const competition =
        escapeHtml(
            match.competition ||
            "Cricket"
        );


    const venue =
        escapeHtml(
            match.venue ||
            "Venue not available"
        );


    const statusText =
        escapeHtml(
            match.status_text ||
            displayStatus(
                match.status,
                section
            )
        );


    const statusClass =
        `status-${safeStatus(
            match.status,
            section
        )}`;


    const timeText =
        formatMatchTime(
            match.start_time,
            section
        );


    return `
        <article class="match-card">

            <div class="match-top">

                <div class="competition">
                    ${competition}
                </div>

                <span
                    class="status-badge ${statusClass}"
                >
                    ${statusText}
                </span>

            </div>


            <div class="teams">

                <div class="team-row">

                    <div class="team-name">
                        ${team1}
                    </div>

                    <div class="team-score">
                        ${score1}
                    </div>

                </div>


                <div class="match-middle">
                    VS
                </div>


                <div class="team-row">

                    <div class="team-name">
                        ${team2}
                    </div>

                    <div class="team-score">
                        ${score2}
                    </div>

                </div>

            </div>


            <div class="match-footer">

                <div class="match-time">
                    ${timeText}
                </div>

                <div class="venue">
                    <span class="venue-icon">
                        📍
                    </span>

                    <span>
                        ${venue}
                    </span>
                </div>

            </div>

        </article>
    `;
}


/* =========================
   SEARCH RESULTS
   ========================= */

function renderSearchResults(
    data
) {
    state.search.active =
        true;


    hideNormalMatches();


    const section =
        document.getElementById(
            "searchSection"
        );

    const results =
        document.getElementById(
            "searchResults"
        );

    const summary =
        document.getElementById(
            "searchSummary"
        );


    if (
        !section ||
        !results ||
        !summary
    ) {
        return;
    }


    section.classList.remove(
        "hidden"
    );


    const upcoming =
        Array.isArray(
            data.upcoming
        )
            ? data.upcoming
            : [];


    const finished =
        Array.isArray(
            data.finished
        )
            ? data.finished
            : [];


    const total =
        safeNumber(
            data?.counts?.total
        );


    summary.textContent =
        `${total} match${total === 1 ? "" : "es"} found for "${data.query}"`;


    let html = "";


    if (upcoming.length > 0) {

        html += `
            <div class="search-result-group">

                <div class="search-result-title">

                    Upcoming

                    <span class="search-result-count">
                        ${upcoming.length}
                    </span>

                </div>

                <div class="match-grid">
                    ${upcoming
                        .map(
                            (match) =>
                                createMatchCard(
                                    match,
                                    "upcoming"
                                )
                        )
                        .join("")}
                </div>

            </div>
        `;
    }


    if (finished.length > 0) {

        html += `
            <div class="search-result-group">

                <div class="search-result-title">

                    Finished

                    <span class="search-result-count">
                        ${finished.length}
                    </span>

                </div>

                <div class="match-grid">
                    ${finished
                        .map(
                            (match) =>
                                createMatchCard(
                                    match,
                                    "finished"
                                )
                        )
                        .join("")}
                </div>

            </div>
        `;
    }


    if (!html) {
        html = `
            <div class="empty-state">
                No upcoming or finished matches found for
                "${escapeHtml(data.query || "")}".
            </div>
        `;
    }


    results.innerHTML =
        html;
}


function renderSearchError(
    message
) {
    const section =
        document.getElementById(
            "searchSection"
        );

    const results =
        document.getElementById(
            "searchResults"
        );


    hideNormalMatches();


    if (!section || !results) {
        return;
    }


    section.classList.remove(
        "hidden"
    );


    results.innerHTML = `
        <div class="empty-state">
            ${escapeHtml(message)}
        </div>
    `;
}


/* =========================
   SHOW / HIDE NORMAL FEED
   ========================= */

function hideNormalMatches() {
    const tabs =
        document.getElementById(
            "matchTabs"
        );


    if (tabs) {
        tabs.classList.add(
            "hidden"
        );
    }


    document
        .querySelectorAll(
            ".match-section"
        )
        .forEach(
            (section) => {
                section.classList.add(
                    "hidden"
                );
            }
        );
}


function showNormalMatches() {
    const tabs =
        document.getElementById(
            "matchTabs"
        );


    if (tabs) {
        tabs.classList.remove(
            "hidden"
        );
    }


    document
        .querySelectorAll(
            ".match-section"
        )
        .forEach(
            (section) => {
                section.classList.remove(
                    "hidden"
                );
            }
        );
}


function hideSearchResults() {
    const section =
        document.getElementById(
            "searchSection"
        );

    const results =
        document.getElementById(
            "searchResults"
        );

    const summary =
        document.getElementById(
            "searchSummary"
        );


    if (section) {
        section.classList.add(
            "hidden"
        );
    }


    if (results) {
        results.innerHTML = "";
    }


    if (summary) {
        summary.textContent = "";
    }
}


/* =========================
   STATUS
   ========================= */

function safeStatus(
    status,
    section
) {
    const value =
        String(
            status ||
            section ||
            ""
        ).toLowerCase();


    if (
        value === "live" ||
        value === "upcoming" ||
        value === "finished"
    ) {
        return value;
    }


    return section;
}


function displayStatus(
    status,
    section
) {
    const value =
        safeStatus(
            status,
            section
        );


    if (value === "live") {
        return "LIVE";
    }


    if (value === "finished") {
        return "FINISHED";
    }


    return "UPCOMING";
}


/* =========================
   TIME
   ========================= */

function formatMatchTime(
    value,
    section
) {
    if (!value) {
        return "";
    }


    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return escapeHtml(
            String(value)
        );
    }


    try {

        const formatted =
            new Intl.DateTimeFormat(
                undefined,
                {
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit"
                }
            ).format(date);


        if (
            section === "live"
        ) {
            return `Started ${formatted}`;
        }


        if (
            section === "finished"
        ) {
            return formatted;
        }


        return formatted;

    } catch (error) {
        return escapeHtml(
            String(value)
        );
    }
}


/* =========================
   UPDATED TIME
   ========================= */

function updateLastUpdated(
    value
) {
    const element =
        document.getElementById(
            "updatedAt"
        );


    if (!element) {
        return;
    }


    if (!value) {
        element.textContent = "—";
        return;
    }


    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        element.textContent =
            "Just now";

        return;
    }


    try {

        element.textContent =
            new Intl.DateTimeFormat(
                undefined,
                {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit"
                }
            ).format(date);

    } catch (error) {

        element.textContent =
            "Just now";
    }
}


/* =========================
   EMPTY STATE
   ========================= */

function emptyMessage(
    section
) {
    if (
        section === "live"
    ) {
        return "No live matches right now.";
    }


    if (
        section === "upcoming"
    ) {
        return "No upcoming matches available.";
    }


    return "No finished matches available.";
}


/* =========================
   ERRORS
   ========================= */

function renderErrors(
    errors
) {
    if (
        !Array.isArray(errors) ||
        errors.length === 0
    ) {
        hideGlobalError();
        return;
    }


    const messages =
        errors
            .map(
                (item) => {
                    const provider =
                        item?.provider ||
                        "Provider";

                    const error =
                        item?.error ||
                        "Unknown error";

                    return `${provider}: ${error}`;
                }
            )
            .join(" | ");


    showGlobalError(
        `Some cricket data sources could not be reached. ${messages}`
    );
}


function showGlobalError(
    message
) {
    const element =
        document.getElementById(
            "globalError"
        );


    if (!element) {
        return;
    }


    element.textContent =
        message;

    element.classList.remove(
        "hidden"
    );
}


function hideGlobalError() {
    const element =
        document.getElementById(
            "globalError"
        );


    if (!element) {
        return;
    }


    element.textContent = "";

    element.classList.add(
        "hidden"
    );
}


/* =========================
   HELPERS
   ========================= */

function safeNumber(
    value
) {
    const number =
        Number(value);

    return Number.isFinite(
        number
    )
        ? number
        : 0;
}


function escapeHtml(
    value
) {
    return String(value)
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );
}


function escapeAttribute(
    value
) {
    return escapeHtml(
        value
    );
}

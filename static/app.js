const state = {
    activeSection: "live",
    matches: {
        live: [],
        upcoming: [],
        finished: []
    }
};


document.addEventListener("DOMContentLoaded", () => {
    setupTabs();
    setupModal();
    loadMatches();

    // Refresh browser data every 60 seconds.
    setInterval(loadMatches, 60 * 1000);
});


function setupTabs() {
    const tabs = document.querySelectorAll(".tab");

    tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            const section = tab.dataset.section;

            if (!section) {
                return;
            }

            switchSection(section);
        });
    });
}


function switchSection(section) {
    state.activeSection = section;

    document.querySelectorAll(".tab").forEach((tab) => {
        tab.classList.toggle(
            "active",
            tab.dataset.section === section
        );
    });

    document.querySelectorAll(".match-section").forEach((element) => {
        const isActive =
            element.id === `${section}Section`;

        element.classList.toggle(
            "active-section",
            isActive
        );
    });
}


function setupModal() {
    document.querySelectorAll("[data-close-modal]").forEach((element) => {
        element.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeModal();
        }
    });
}


async function loadMatches() {
    setConnection("loading");

    try {
        const response = await fetch(
            "/api/matches",
            {
                method: "GET",
                headers: {
                    "Accept": "application/json"
                },
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                `Server returned ${response.status}`
            );
        }

        const data = await response.json();

        if (!data.ok) {
            throw new Error(
                data.error || "Unable to load matches"
            );
        }

        state.matches.live = Array.isArray(data.live)
            ? data.live
            : [];

        state.matches.upcoming = Array.isArray(data.upcoming)
            ? data.upcoming
            : [];

        state.matches.finished = Array.isArray(data.finished)
            ? data.finished
            : [];

        renderCounts(data.counts || {});
        renderMatches("live", state.matches.live);
        renderMatches("upcoming", state.matches.upcoming);
        renderMatches("finished", state.matches.finished);

        updateLastUpdated(data.updated_at);

        renderErrors(data.errors || []);

        setConnection("online");

    } catch (error) {
        console.error("CrixData API error:", error);

        setConnection("offline");

        showGlobalError(
            "Unable to load cricket data right now. Please try again."
        );

        renderMatches("live", []);
        renderMatches("upcoming", []);
        renderMatches("finished", []);
    }
}


function setConnection(status) {
    const dot = document.getElementById("connectionDot");
    const text = document.getElementById("connectionText");

    if (!dot || !text) {
        return;
    }

    dot.classList.remove(
        "online",
        "offline"
    );

    if (status === "online") {
        dot.classList.add("online");
        text.textContent = "Live connection";
        return;
    }

    if (status === "offline") {
        dot.classList.add("offline");
        text.textContent = "Connection error";
        return;
    }

    text.textContent = "Updating...";
}


function renderCounts(counts) {
    document.getElementById("liveCount").textContent =
        safeNumber(counts.live);

    document.getElementById("upcomingCount").textContent =
        safeNumber(counts.upcoming);

    document.getElementById("finishedCount").textContent =
        safeNumber(counts.finished);
}


function renderMatches(section, matches) {
    const container = document.getElementById(
        `${section}Matches`
    );

    if (!container) {
        return;
    }

    if (!matches.length) {
        container.innerHTML = `
            <div class="empty-state">
                ${emptyMessage(section)}
            </div>
        `;

        return;
    }

    container.innerHTML = matches
        .map((match) => createMatchCard(match, section))
        .join("");

    container.querySelectorAll(".details-button").forEach((button) => {
        button.addEventListener("click", () => {
            const matchId = button.dataset.matchId;

            if (matchId) {
                openDetails(matchId);
            }
        });
    });
}


function emptyMessage(section) {
    if (section === "live") {
        return "No live matches right now.";
    }

    if (section === "upcoming") {
        return "No upcoming matches available.";
    }

    return "No finished matches available.";
}


function createMatchCard(match, section) {
    const team1 = escapeHtml(
        match.team1 || "Team 1"
    );

    const team2 = escapeHtml(
        match.team2 || "Team 2"
    );

    const score1 = escapeHtml(
        match.team1_score || ""
    );

    const score2 = escapeHtml(
        match.team2_score || ""
    );

    const competition = escapeHtml(
        match.competition || "Cricket"
    );

    const venue = escapeHtml(
        match.venue || ""
    );

    const statusText = escapeHtml(
        match.status_text || displayStatus(match.status, section)
    );

    const statusClass =
        `status-${safeStatus(match.status, section)}`;

    const timeText = formatMatchTime(
        match.start_time,
        section
    );

    const detailsButton = match.details_url || match.provider
        ? `
            <button
                type="button"
                class="details-button"
                data-match-id="${escapeAttribute(match.id || "")}"
            >
                Details
            </button>
        `
        : "";

    return `
        <article class="match-card">

            <div class="match-top">

                <div class="competition">
                    ${competition}
                </div>

                <span class="status-badge ${statusClass}">
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

                <div class="match-meta">
                    ${timeText || venue || "Match information"}
                </div>

                ${detailsButton}

            </div>

        </article>
    `;
}


function safeStatus(status, section) {
    const value = String(status || section).toLowerCase();

    if (
        value === "live" ||
        value === "upcoming" ||
        value === "finished"
    ) {
        return value;
    }

    return section;
}


function displayStatus(status, section) {
    const value = safeStatus(status, section);

    if (value === "live") {
        return "LIVE";
    }

    if (value === "finished") {
        return "FINISHED";
    }

    return "UPCOMING";
}


function formatMatchTime(value, section) {
    if (!value) {
        return "";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return escapeHtml(String(value));
    }

    try {
        const formatted = new Intl.DateTimeFormat(
            undefined,
            {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit"
            }
        ).format(date);

        if (section === "live") {
            return `Started ${formatted}`;
        }

        if (section === "finished") {
            return formatted;
        }

        return formatted;

    } catch (error) {
        return escapeHtml(String(value));
    }
}


function updateLastUpdated(value) {
    const element = document.getElementById("updatedAt");

    if (!element) {
        return;
    }

    if (!value) {
        element.textContent = "—";
        return;
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        element.textContent = "Just now";
        return;
    }

    try {
        element.textContent = new Intl.DateTimeFormat(
            undefined,
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        ).format(date);

    } catch (error) {
        element.textContent = "Just now";
    }
}


function renderErrors(errors) {
    if (!Array.isArray(errors) || errors.length === 0) {
        hideGlobalError();
        return;
    }

    const messages = errors
        .map((item) => {
            const provider = item?.provider || "Provider";
            const error = item?.error || "Unknown error";

            return `${provider}: ${error}`;
        })
        .join(" | ");

    showGlobalError(
        `Some cricket data sources could not be reached. ${messages}`
    );
}


function showGlobalError(message) {
    const element = document.getElementById("globalError");

    if (!element) {
        return;
    }

    element.textContent = message;
    element.classList.remove("hidden");
}


function hideGlobalError() {
    const element = document.getElementById("globalError");

    if (!element) {
        return;
    }

    element.textContent = "";
    element.classList.add("hidden");
}


async function openDetails(matchId) {
    const modal = document.getElementById("detailsModal");
    const content = document.getElementById("detailsContent");

    if (!modal || !content) {
        return;
    }

    modal.classList.remove("hidden");

    content.innerHTML = `
        <div class="loading">
            Loading match details...
        </div>
    `;

    try {
        const response = await fetch(
            `/api/matches/${encodeURIComponent(matchId)}/details`,
            {
                method: "GET",
                headers: {
                    "Accept": "application/json"
                },
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                `Server returned ${response.status}`
            );
        }

        const data = await response.json();

        if (!data.ok) {
            throw new Error(
                data.error || "Unable to load details"
            );
        }

        content.innerHTML = createDetailsView(
            data.details || {},
            matchId
        );

    } catch (error) {
        console.error("Details error:", error);

        content.innerHTML = `
            <div class="empty-state">
                Unable to load match details.
            </div>
        `;
    }
}


function createDetailsView(details, matchId) {
    const safeId = escapeHtml(matchId);

    const values = flattenDetails(
        details,
        0,
        "",
        []
    );

    const rows = values.length
        ? values.slice(0, 40).map((item) => `
            <div class="detail-item">

                <div class="detail-label">
                    ${escapeHtml(item.key)}
                </div>

                <div class="detail-value">
                    ${escapeHtml(item.value)}
                </div>

            </div>
        `).join("")
        : `
            <div class="empty-state">
                No additional details available.
            </div>
        `;

    return `
        <h3 class="details-title">
            Match Details
        </h3>

        <div
            class="detail-item"
            style="margin-bottom: 12px;"
        >
            <div class="detail-label">
                Match ID
            </div>

            <div class="detail-value">
                ${safeId}
            </div>
        </div>

        <div class="details-grid">
            ${rows}
        </div>
    `;
}


function flattenDetails(
    value,
    depth,
    prefix,
    output
) {
    if (depth > 3) {
        return output;
    }

    if (
        value === null ||
        value === undefined
    ) {
        return output;
    }

    if (Array.isArray(value)) {
        value.forEach((item, index) => {
            flattenDetails(
                item,
                depth + 1,
                prefix
                    ? `${prefix}.${index + 1}`
                    : `${index + 1}`,
                output
            );
        });

        return output;
    }

    if (
        typeof value === "object"
    ) {
        Object.entries(value).forEach(
            ([key, item]) => {
                const nextPrefix = prefix
                    ? `${prefix}.${key}`
                    : key;

                if (
                    item !== null &&
                    typeof item === "object"
                ) {
                    flattenDetails(
                        item,
                        depth + 1,
                        nextPrefix,
                        output
                    );
                } else {
                    output.push({
                        key: nextPrefix,
                        value: String(item ?? "")
                    });
                }
            }
        );

        return output;
    }

    output.push({
        key: prefix || "value",
        value: String(value)
    });

    return output;
}


function closeModal() {
    const modal = document.getElementById("detailsModal");

    if (!modal) {
        return;
    }

    modal.classList.add("hidden");
}


function safeNumber(value) {
    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : 0;
}


function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function escapeAttribute(value) {
    return escapeHtml(value);
}
